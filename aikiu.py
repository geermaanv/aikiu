"""
Aikiu — Asistente de voz para adultos mayores via Telegram
STT + LLM: Groq (free tier)
TTS: Telegram voice notes nativos
Sin Ollama, sin Whisper local, sin servidor propio.
"""

import asyncio
import json
import logging
import re
import tempfile
import os
import yaml
import httpx
from datetime import datetime, date, timedelta
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, BotCommand, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import AsyncGroq
from openai import AsyncOpenAI
from core.distress import (
    parse_llm_response, parse_distress_classification,
    should_send_alert, record_alert_sent,
)
from core.alerts import notify_family, notify_inactividad
from core.tts import sintetizar
from core.tools import consultar_clima, consultar_dolar, consultar_noticias, titulares_google_news
from core import state as state_mod
from core import heartbeat as hb_mod
from core import usage as usage_mod
from core import hogar as hogar_mod
from core import migrate_legacy
from core import invites as invites_mod
from core.utils import (
    norm, load_json, nombre_adulto, read_section,
    fecha_hora_es, fecha_en_espanol,
    write_json_atomic, write_text_atomic,
    CLIMA_KEYWORDS, DOLAR_KEYWORDS, NOTICIAS_KEYWORDS,
)
from typing import Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# mtime de perfil.md / aikiu_core.md al momento de la última lectura.
# Permite el hot-reload: si el archivo cambió en disco, se recarga en CONFIG
# sin reiniciar el bot (ver _refrescar_config_desde_disco).
_config_mtimes: dict = {}


def cargar_config():
    with open(BASE_DIR / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Variables obligatorias: solo el token del bot y la API key del LLM.
    # El chat_id del adulto se autoregistra en el primer /start (ver core/state.py),
    # pero si está en .env se respeta como override (compat con instalaciones viejas).
    for key, env_var in [("bot_token", "BOT_TOKEN"), ("groq_api_key", "GROQ_API_KEY")]:
        value = os.environ.get(env_var, "").strip()
        if not value or "PEGA_TU" in value:
            raise RuntimeError(f"Falta la variable de entorno {env_var} (definila en .env)")
        cfg[key] = value
    perfil_path = BASE_DIR / cfg.get("perfil", "perfil.md")
    if perfil_path.exists():
        cfg["_perfil"] = perfil_path.read_text(encoding="utf-8")
        _config_mtimes["_perfil"] = perfil_path.stat().st_mtime
    else:
        cfg["_perfil"] = ""
    core_path = BASE_DIR / "aikiu_core.md"
    if core_path.exists():
        cfg["_core"] = core_path.read_text(encoding="utf-8")
        _config_mtimes["_core"] = core_path.stat().st_mtime
    else:
        cfg["_core"] = ""
    return cfg

CONFIG = cargar_config()


def _refrescar_config_desde_disco() -> None:
    """
    Hot-reload de perfil.md (legacy) y aikiu_core.md: si el archivo cambió
    en disco desde la última lectura (mtime distinto), recarga el contenido
    en CONFIG. Así los aprendizajes del análisis nocturno y las ediciones
    del bot familiar entran al system prompt sin reiniciar el bot.

    Un CONFIG["_perfil"] / CONFIG["_core"] pisado en memoria (tests) se
    respeta mientras el archivo no cambie, porque el mtime no varía.
    """
    rutas = {
        "_perfil": BASE_DIR / CONFIG.get("perfil", "perfil.md"),
        "_core": BASE_DIR / "aikiu_core.md",
    }
    for clave, path in rutas.items():
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if _config_mtimes.get(clave) != mtime:
            try:
                CONFIG[clave] = path.read_text(encoding="utf-8")
                _config_mtimes[clave] = mtime
                log.info(f"Hot-reload: {path.name} recargado en {clave}")
            except OSError as e:
                log.warning(f"Hot-reload: no pude releer {path.name}: {e}")

from logging.handlers import RotatingFileHandler


class _RedactarToken(logging.Filter):
    """Reemplaza el token del bot en los logs. El logger de httpx registra
    cada getUpdates con el token en texto plano — miles de veces. Si se
    comparten logs (a un inversor, en un issue), el token viajaba adentro."""
    _re = re.compile(r"(bot)\d{6,}:[\w-]{20,}")

    def filter(self, record: logging.LogRecord) -> bool:
        # El token puede estar en msg o en los args (httpx pone la URL en args).
        if isinstance(record.msg, str):
            record.msg = self._re.sub(r"\1<REDACTED>", record.msg)
        if record.args:
            record.args = tuple(
                self._re.sub(r"\1<REDACTED>", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


# Rotación: aikiu.log llegaba a decenas de MB y crecía sin límite.
# 5 MB por archivo, 3 backups → tope de ~20 MB.
_file_handler = RotatingFileHandler(
    BASE_DIR / "aikiu.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
)
_redactar = _RedactarToken()
_file_handler.addFilter(_redactar)
_stream_handler = logging.StreamHandler()
_stream_handler.addFilter(_redactar)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[_stream_handler, _file_handler],
)
log = logging.getLogger("aikiu")


# ---------------------------------------------------------------------------
# Resolvers por hogar (multi-tenant)
# ---------------------------------------------------------------------------
# Estos helpers devuelven la "vista" del config / perfil para un chat_id
# específico. La idea es: hay un `config.yml` global que actúa como TEMPLATE
# (defaults para nombre del adulto, ciudad, voz, etc.). Cada hogar puede
# pisar campos en su `instances/<chat_id>/state.json` (clave por clave).
#
# Las funciones de negocio reciben `chat_id` como parámetro opcional:
#   - Si se pasa, usan la vista del hogar (multi-tenant).
#   - Si no, leen el CONFIG global (modo legacy / test).
#
# Esto permite que la suite de tests viejos siga andando sin tocar nada.

_PERFIL_TEMPLATE_PATH = BASE_DIR / CONFIG.get("perfil", "perfil.md")


def _state_hogar(chat_id: int) -> dict:
    """Lee el `state.json` del hogar. {} si no existe."""
    return hogar_mod.leer_state(chat_id)


def _config_hogar(chat_id: int) -> dict:
    """
    Devuelve la vista de configuración para un hogar:
    template global (CONFIG) con los campos del `state.json` del hogar
    encima como overrides.

    Campos overrideables (todos opcionales en el state):
        nombre_adulto_mayor, nombre_asistente, ciudad, voz_tts

    Compat: si el state tiene `nombre_adulto` (clave que persiste
    `crear_hogar` con el first_name de Telegram en el /start) y no tiene
    `nombre_adulto_mayor`, lo promovemos. Así un hogar nuevo que solo
    pasó por el alta automática ya muestra el nombre del usuario en vez
    de caer al fallback del template global.
    """
    vista = dict(CONFIG)
    estado = _state_hogar(chat_id)
    for clave in ("nombre_adulto_mayor", "nombre_asistente", "ciudad", "voz_tts"):
        if clave in estado:
            vista[clave] = estado[clave]
    if "nombre_adulto_mayor" not in estado and estado.get("nombre_adulto"):
        vista["nombre_adulto_mayor"] = estado["nombre_adulto"]
    return vista


def _perfil_hogar(chat_id: int) -> str:
    """
    Lee `instances/<chat_id>/perfil.md`. Si no existe, lo crea copiando el
    template global y devuelve el texto. Si tampoco hay template, devuelve "".
    """
    path = hogar_mod.perfil_path(chat_id)
    if path.exists():
        return path.read_text(encoding="utf-8")
    if _PERFIL_TEMPLATE_PATH.exists():
        contenido = _PERFIL_TEMPLATE_PATH.read_text(encoding="utf-8")
        try:
            write_text_atomic(path, contenido)
        except OSError as e:
            log.warning(f"No pude inicializar perfil para hogar {chat_id}: {e}")
        return contenido
    return ""


def _nombre_adulto_de(chat_id: Optional[int]) -> str:
    if chat_id is None:
        return CONFIG.get("nombre_adulto_mayor", "") or ""
    return _config_hogar(chat_id).get("nombre_adulto_mayor", "") or ""


def _nombre_asistente_de(chat_id: Optional[int]) -> str:
    if chat_id is None:
        return CONFIG.get("nombre_asistente", "Aikiu")
    return _config_hogar(chat_id).get("nombre_asistente", "Aikiu")


def _ciudad_de(chat_id: Optional[int]) -> str:
    if chat_id is None:
        return CONFIG.get("ciudad", "Buenos Aires")
    return _config_hogar(chat_id).get("ciudad", "Buenos Aires")


def _voz_tts_de(chat_id: Optional[int]) -> str:
    if chat_id is None:
        return CONFIG.get("voz_tts", "es-AR-ElenaNeural")
    return _config_hogar(chat_id).get("voz_tts", "es-AR-ElenaNeural")


def _medio_de(chat_id: Optional[int]) -> str:
    """Medio preferido del hogar: 'texto' o 'voz'. Default 'texto' mientras
    iteramos la conversación (la voz de edge-tts suena metálica). Editable en
    config.yml (global) o en el state del hogar."""
    if chat_id is None:
        return CONFIG.get("medio", "texto")
    return _config_hogar(chat_id).get("medio", "texto")


def _asegurar_hogar(chat_id: int, *, nombre_tg: Optional[str] = None) -> bool:
    """
    Crea `instances/<chat_id>/` si no existe. Devuelve True si era nuevo.

    Cualquier mensaje al bot global de un chat_id desconocido dispara el alta
    automática (self-service onboarding). El template de config global queda
    activo; el adulto puede personalizar después editando perfil o state.
    """
    if hogar_mod.existe_hogar(chat_id):
        return False
    # Si el caller nos pasó algo que no es string (mocks, None, etc.) lo
    # descartamos antes de persistir.
    nombre_seguro = nombre_tg if isinstance(nombre_tg, str) else None
    hogar_mod.crear_hogar(chat_id, nombre=nombre_seguro)
    log.warning(
        f"[HOGAR NUEVO] chat_id={chat_id} usuario_tg={nombre_seguro!r} "
        f"hora={datetime.now().isoformat(timespec='seconds')}"
    )
    return True

# Cliente Groq: siempre necesario para STT (Whisper large-v3). También hace
# de LLM de chat cuando proveedor_llm == "groq".
groq = AsyncGroq(api_key=CONFIG["groq_api_key"])

# Cliente OpenRouter (OpenAI-compatible): LLM de chat cuando
# proveedor_llm == "openrouter". La key puede faltar si el proveedor es groq;
# main() valida la combinación al arranque.
# Placeholder si falta la key: el SDK de OpenAI lanza al construir con key
# vacía, y eso rompía el import en CI (donde no hay OPENROUTER_API_KEY). Con
# proveedor openrouter, main() valida la key real al arrancar; en tests las
# llamadas están mockeadas, así que el cliente nunca hace un request real.
openrouter = AsyncOpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY") or "sk-or-placeholder",
    base_url="https://openrouter.ai/api/v1",
)


# Timeout por llamada al LLM de chat. El default del SDK es 10 min: si
# OpenRouter se cuelga, el adulto esperaría eternamente. 20s es de sobra
# para una respuesta de 300 tokens y corta rápido ante un hipo del proveedor.
_LLM_TIMEOUT_S = 20
# Modelo de respaldo en Groq si OpenRouter falla o tarda (rápido y siempre up).
_FALLBACK_MODELO = "llama-3.3-70b-versatile"


async def _chat_create(**kwargs):
    """
    Punto único de acceso al LLM de chat. Despacha según CONFIG["proveedor_llm"]
    ("groq" por default, compat con instalaciones y tests existentes).

    Con OpenRouter apaga el razonamiento de los modelos que lo traen (GLM-5):
    el "pensamiento" consume el max_tokens (deja content vacío) y agrega una
    latencia que la conversación de voz no tolera.

    Si OpenRouter falla o supera el timeout, cae automáticamente a Groq/Llama
    para que el adulto reciba SIEMPRE una respuesta. Nunca deja al usuario
    colgado por un problema del proveedor.
    """
    proveedor = CONFIG.get("proveedor_llm", "groq")
    if proveedor == "openrouter":
        or_kwargs = dict(kwargs)
        or_kwargs.setdefault("extra_body", {"reasoning": {"enabled": False}})
        try:
            return await asyncio.wait_for(
                openrouter.chat.completions.create(**or_kwargs),
                timeout=_LLM_TIMEOUT_S,
            )
        except Exception as e:
            log.warning(f"OpenRouter falló ({type(e).__name__}: {str(e)[:80]}) → fallback a Groq/{_FALLBACK_MODELO}")
            groq_kwargs = {k: v for k, v in kwargs.items() if k != "extra_body"}
            groq_kwargs["model"] = _FALLBACK_MODELO
            return await asyncio.wait_for(
                groq.chat.completions.create(**groq_kwargs), timeout=_LLM_TIMEOUT_S
            )
    return await asyncio.wait_for(
        groq.chat.completions.create(**kwargs), timeout=_LLM_TIMEOUT_S
    )


# Referencia fuerte a tasks en background para evitar que el GC los cancele
_background_tasks: set = set()

def create_background_task(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

# ---------------------------------------------------------------------------
# STT: Groq Whisper
# ---------------------------------------------------------------------------

async def transcribir(ogg_path: Path) -> str:
    bytes_audio = ogg_path.stat().st_size if ogg_path.exists() else 0
    async with usage_mod.timed_stt("whisper-large-v3", bytes_audio):
        with open(ogg_path, "rb") as f:
            result = await groq.audio.transcriptions.create(
                file=(ogg_path.name, f, "audio/ogg"),
                model="whisper-large-v3",
                language="es",
                response_format="text",
            )
    texto = result.strip() if isinstance(result, str) else result.text.strip()
    log.info(f"STT: '{texto}'")
    return texto

# ---------------------------------------------------------------------------
# LLM: Groq llama-3.3-70b
# ---------------------------------------------------------------------------



def construir_system_prompt(perfil: str, core: str, asistente: str, nombre: str) -> str:
    partes = [f"Tu nombre es {asistente}. Hablás con {nombre}.\n"]

    if core:
        partes.append(f"## LINEAMIENTOS DEL SISTEMA\n{core}\n")

    if perfil:
        partes.append(f"## PERFIL DE {nombre.upper()}\n{perfil}\n")
    else:
        partes.append(
            f"Sos {asistente}, un asistente de voz para {nombre}. "
            f"Respondé en español rioplatense, oraciones cortas y simples. "
            f"Nunca uses markdown. Máximo 3 oraciones.\n"
        )

    partes.append(f"Fecha y hora actual: {fecha_hora_es()} (hora de Buenos Aires).\n")
    partes.append(
        "\n---\n"
        "INSTRUCCIÓN DE SISTEMA (nunca leer en voz alta ni mencionar al usuario):\n"
        "- Cuando el mensaje incluya datos en tiempo real (clima, dólar, noticias),\n"
        "  están provistos justo antes del mensaje del usuario. Usálos para responder\n"
        "  con los valores exactos (°C, pesos). No los inventes si no están presentes.\n"
        f"- No tenés información sobre mensajes de familiares. Solo si {nombre} pregunta\n"
        "  específicamente si alguien le escribió o mandó un mensaje, respondé:\n"
        "  'No recibí ningún mensaje para vos hoy.' Nunca inventes ni supongas.\n"
        # La detección de angustia (DISTRESS) ya NO vive acá: la hace el agente
        # vigía (clasificar_distress), una llamada separada. El conversador solo
        # conversa. Ver handle_message.
    )
    return "".join(partes)


async def _pre_route(texto: str, chat_id: Optional[int] = None) -> str:
    """Detecta si el mensaje requiere datos externos y los obtiene antes del LLM."""
    t = norm(texto)
    if any(w in t for w in CLIMA_KEYWORDS):
        ciudad = _ciudad_de(chat_id)
        # Detectar ciudad mencionada explícitamente: "en Córdoba", "en Mendoza"
        m = re.search(r"\ben\s+([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+)?)", texto)
        if m:
            ciudad = m.group(1)
        resultado = await consultar_clima(ciudad)
        log.info(f"Pre-route clima({ciudad}) → {resultado[:80]}")
        return resultado

    if any(w in t for w in DOLAR_KEYWORDS):
        resultado = await consultar_dolar()
        log.info(f"Pre-route dolar → {resultado[:80]}")
        return resultado

    if any(w in t for w in NOTICIAS_KEYWORDS):
        resultado = await consultar_noticias()
        log.info(f"Pre-route noticias → {resultado[:80]}")
        return resultado

    return ""


async def generar_respuesta(
    texto_usuario: str,
    historial: list,
    chat_id: Optional[int] = None,
) -> str:
    _refrescar_config_desde_disco()
    if chat_id is None:
        asistente = CONFIG["nombre_asistente"]
        nombre    = CONFIG["nombre_adulto_mayor"]
        perfil    = CONFIG.get("_perfil", "")
    else:
        asistente = _nombre_asistente_de(chat_id)
        nombre    = _nombre_adulto_de(chat_id)
        perfil    = _perfil_hogar(chat_id)
    core          = CONFIG.get("_core", "")
    system_prompt = construir_system_prompt(perfil, core, asistente, nombre)
    modelo        = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial[-20:])

    # Pre-routing: obtener datos externos antes del LLM
    datos_externos = await _pre_route(texto_usuario, chat_id=chat_id)
    if datos_externos:
        messages.append({
            "role": "system",
            "content": f"Datos en tiempo real para responder este mensaje: {datos_externos}",
        })

    # RULE_MEM_01: inyectar temática activa (continuidad afectiva entre sesiones)
    tematica = load_json(_tematica_activa_path(chat_id), default={})
    temas_activos = tematica.get("temas", [])
    if temas_activos:
        messages.append({
            "role": "system",
            "content": f"TEMÁTICA_ACTIVA: {', '.join(temas_activos)}. "
                       f"Si {nombre} menciona estos temas, usá verbos de continuidad y familiaridad, "
                       f"no de descubrimiento. Ejemplo: 'Qué lindo que sigan así de fuertes' en vez de '¡Qué lindas tus plantas!'.",
        })

    # RULE_TIME_22: modo nocturno (después de 21hs)
    hora_actual = datetime.now().hour
    if hora_actual >= 21 or hora_actual < 6:
        messages.append({
            "role": "system",
            "content": "Es de noche. Respondé con calma y serenidad, sin proponer actividades dinámicas. "
                       "Usá palabras que evoquen el descanso y la tranquilidad.",
        })

    # Inyectar blacklist de temas con baja receptividad en las últimas 48h
    evitar = _temas_a_evitar(chat_id=chat_id)
    if evitar:
        messages.append({
            "role": "system",
            "content": f"Temas a evitar en esta respuesta (baja receptividad reciente de {nombre}): "
                       f"{', '.join(evitar)}. No los sugieras ni los menciones.",
        })

    # Inyectar temas de alto engagement como sugerencia de iniciativa
    preferidos = _temas_preferidos(chat_id=chat_id)
    preferidos_filtrados = [t for t in preferidos if t not in evitar]
    if preferidos_filtrados:
        messages.append({
            "role": "system",
            "content": f"Temas con alto engagement reciente de {nombre} (úsalos si la conversación se frena): "
                       f"{', '.join(preferidos_filtrados[:3])}.",
        })

    # Contexto del día (actualidad curada de madrugada + dólar + clima). Sirve
    # para responder si pregunta Y para traer temas a la charla por iniciativa.
    contexto = _texto_contexto_del_dia(chat_id)
    if contexto:
        messages.append({
            "role": "system",
            "content": (
                f"Contexto de actualidad de HOY ({fecha_en_espanol()}) — es la única "
                f"fuente válida para lo que pasa hoy. Usalo si {nombre} pregunta, o "
                f"para traer un tema liviano si la charla se frena (sin forzar):\n{contexto}"
            ),
        })

    # El historial puede abarcar varios días: lo que era "hoy" en una charla vieja
    # (un partido, un turno, una visita) NO sigue siendo hoy. Sin esta aclaración,
    # el modelo repite datos con fecha del historial como si fueran actuales.
    messages.append({
        "role": "system",
        "content": (
            f"Hoy es {fecha_en_espanol()}. El historial de esta conversación puede "
            f"incluir charlas de días anteriores: NO asumas que un dato con fecha que "
            f"aparece ahí (partidos, turnos, planes, 'hoy viene X') siga vigente hoy. "
            f"Para lo de hoy vale solo el contexto de actualidad; si no lo tenés, "
            f"decilo con honestidad en vez de repetir algo viejo."
        ),
    })

    messages.append({"role": "user", "content": texto_usuario})

    # Género: el núcleo está redactado en femenino (la base tiende a mujeres
    # mayores). Si el adulto es hombre, inyectamos una directiva fuerte para
    # que GLM lo trate en masculino pese al núcleo. Para mujeres no hace falta.
    genero = _genero_de(chat_id)
    if genero == "M":
        messages.append({
            "role": "system",
            "content": (
                f"IMPORTANTE: {nombre} es un HOMBRE. Dirigite a él SIEMPRE en masculino "
                "(adjetivos y participios: 'tranquilo', 'solo', 'cansado', 'querido', "
                "'acostumbrado'; nunca en femenino). El texto del sistema usa ejemplos "
                "en femenino porque están pensados para otra persona: adaptalos al masculino."
            ),
        })

    # Recordatorio por turno: el texto para el adulto nunca puede ir vacío,
    # aunque cierre con un monosílabo. (La clasificación de angustia ya no se
    # pide acá — la hace el agente vigía por separado.)
    messages.append({
        "role": "system",
        "content": (
            f"Recordá: siempre respondé a {nombre} con al menos una frase cálida, "
            "nunca con un mensaje vacío, aunque cierre con un monosílabo."
        ),
    })

    try:
        async with usage_mod.timed_chat(modelo) as t:
            response = await _chat_create(
                model=modelo,
                messages=messages,
                max_tokens=300,
                temperature=0.7,
            )
            t.set_usage(response.usage)
        respuesta = (response.choices[0].message.content or "").strip()
    except Exception as e:
        log.warning(f"generar_respuesta: el LLM falló ({type(e).__name__}: {str(e)[:80]})")
        respuesta = ""

    # Nunca devolver vacío: si el LLM falló o vino sin contenido, una frase
    # cálida de respaldo. Marta siempre recibe algo, jamás silencio.
    if not respuesta:
        respuesta = "Perdoná, se me trabó la palabra por un momento. ¿Me lo contás de nuevo?"
    log.info(f"LLM raw: '{respuesta}'")
    return respuesta

# ---------------------------------------------------------------------------
# Estado de conversación e inactividad
# ---------------------------------------------------------------------------

# Caché en RAM del historial por hogar. Se hidrata de disco la primera vez
# (ver _get_historial) para que la conversación sobreviva a reinicios.
historiales: dict[int, list] = {}

# Cuántos mensajes (user+assistant) se conservan. 40 = ~20 turnos. Acota el
# crecimiento en RAM/disco y el tamaño del prompt.
_HISTORIAL_MAX = 40


def _historial_path(chat_id: Optional[int]) -> Path:
    if chat_id is None:
        return BASE_DIR / "historial.json"
    return hogar_mod.historial_path(chat_id)


def _get_historial(chat_id: Optional[int]) -> list:
    """Devuelve el historial del hogar, hidratándolo de disco la primera vez.
    Así la conversación no se pierde al reiniciar el bot."""
    key = chat_id if chat_id is not None else 0
    if key not in historiales:
        historiales[key] = load_json(_historial_path(chat_id), default=[]) or []
    return historiales[key]


def _persistir_historial(chat_id: Optional[int], historial: list) -> None:
    """Poda a los últimos _HISTORIAL_MAX mensajes y escribe a disco."""
    if len(historial) > _HISTORIAL_MAX:
        del historial[:-_HISTORIAL_MAX]
    try:
        write_json_atomic(_historial_path(chat_id), historial)
    except OSError as e:
        log.warning(f"No pude persistir el historial de {chat_id}: {e}")

# Multi-tenant: una última actividad por hogar. El global `_ultima_actividad`
# se mantiene como espejo del último mensaje recibido entre TODOS los hogares
# (para compat con tests existentes que lo monkeypatchean).
_ultima_actividad: datetime | None = None
_ultimas_actividades: dict[int, datetime] = {}
_alertas_inactividad_fecha: dict[int, object] = {}
_alerta_inactividad_fecha: object = None  # legacy global (espejo del default)

# ---------------------------------------------------------------------------
# Log diario y aprendizajes
# ---------------------------------------------------------------------------

# Paths legacy / fallback. Cuando chat_id se pasa explícitamente, las
# funciones usan los paths del hogar (`instances/<chat_id>/...`) y estos
# atributos quedan ignorados. Se mantienen para retrocompatibilidad con
# tests que los monkeypatchean directamente.
PERFIL_PATH       = BASE_DIR / "perfil.md"
LOGS_DIR          = BASE_DIR / "logs"
STATS_PATH        = BASE_DIR / "stats.json"
RECEPTIVIDAD_PATH = BASE_DIR / "receptividad.json"


def _logs_dir(chat_id: Optional[int]) -> Path:
    return hogar_mod.logs_dir(chat_id) if chat_id is not None else LOGS_DIR


def _stats_path(chat_id: Optional[int]) -> Path:
    return hogar_mod.stats_path(chat_id) if chat_id is not None else STATS_PATH


def _receptividad_path(chat_id: Optional[int]) -> Path:
    return hogar_mod.receptividad_path(chat_id) if chat_id is not None else RECEPTIVIDAD_PATH


def _perfil_path(chat_id: Optional[int]) -> Path:
    return hogar_mod.perfil_path(chat_id) if chat_id is not None else PERFIL_PATH


def registrar_log(usuario: str, respuesta: str, chat_id: Optional[int] = None):
    now = datetime.now()
    logs_dir = _logs_dir(chat_id)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{now.strftime('%Y-%m-%d')}.md"
    encabezado = f"# Conversaciones del {now.strftime('%d/%m/%Y')}\n\n"
    nombre = _nombre_adulto_de(chat_id)
    asistente = _nombre_asistente_de(chat_id)
    entrada = f"**{now.strftime('%H:%M')}**\n- {nombre}: {usuario}\n- {asistente}: {respuesta}\n\n"
    if not log_file.exists():
        log_file.write_text(encabezado + entrada, encoding="utf-8")
    else:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entrada)

def registrar_stats(distress_level: int, chat_id: Optional[int] = None):
    """Acumula estadísticas diarias en stats.json para el dashboard familiar."""
    now = datetime.now()
    hoy = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M")
    stats_path = _stats_path(chat_id)
    stats = load_json(stats_path)

    # El día puede haber sido creado por otro código (ej. análisis nocturno)
    # sin todas las claves — accedemos de forma defensiva, nunca con índice
    # directo, para no romper el turno (y de paso la alerta).
    dia = stats.setdefault(hoy, {})
    dia["primer_mensaje"] = dia.get("primer_mensaje", hora)
    dia["mensajes"] = dia.get("mensajes", 0) + 1
    dia["ultimo_mensaje"] = hora
    dia.setdefault("distress", {"1": 0, "2": 0, "3": 0})
    if distress_level >= 1:
        dia["distress"][str(distress_level)] = dia["distress"].get(str(distress_level), 0) + 1

    write_json_atomic(stats_path, stats)


def _prompt_vigia(texto_usuario: str, nombre: str = "Marta") -> str:
    """Prompt del agente vigía (clasificador de distress). Función pura,
    separada para poder testear los criterios sin llamar al LLM."""
    return (
        f"Sos un evaluador de riesgo emocional. Leé ÚNICAMENTE este último mensaje "
        f"de {nombre} (una persona mayor) y clasificá su nivel de angustia según su "
        f"propio estado. No conversás, solo clasificás.\n\n"
        f"Mensaje actual de {nombre}: {texto_usuario}\n\n"
        f"Respondé EXACTAMENTE dos líneas:\n"
        f"NIVEL: (un dígito 0-3)\n"
        f"MOTIVO: (frase corta que le sirva a la familia, ej: 'mencionó una caída y dolor de cadera')\n\n"
        f"Criterios (evaluá solo lo que {nombre} dice de su propio estado en este mensaje actual;\n"
        f"un saludo o pregunta neutra es nivel 0 aunque antes haya habido una emergencia):\n"
        f"- 0: saludo, pregunta informativa, charla cotidiana, o cualquier mensaje ambiguo o sin señal. "
        f"OJO: hacer o planear una actividad en soledad ('voy a ver el partido solo', 'cené sola', "
        f"'paso la tarde tranquilo en casa') NO es angustia — es un hecho cotidiano, es nivel 0. "
        f"Solo cuenta como señal si {nombre} EXPRESA que ESO le pesa o lo entristece.\n"
        f"- 1: expresa SENTIRSE solo/triste o que algo le pesa emocionalmente ('me siento muy solo', "
        f"'estoy triste', 'extraño a alguien', 'no pude dormir') — un sentimiento, no un dato; O "
        f"menciona un golpe, tropezón o dolor físico reciente aunque lo minimice ('me golpeé', "
        f"'me pegué', 'me duele un poco') — la familia debe enterarse aunque {nombre} le reste importancia\n"
        f"- 2: llora, dice que está muy mal, dolor físico que PERSISTE, se repite o empeora "
        f"('me sigue doliendo', 'cada vez peor'), confusión/desorientación, menciona una CAÍDA "
        f"(aunque haya pasado), dice 'soy una carga'\n"
        f"- 3: emergencia activa ahora: no puede moverse, dolor de pecho, no puede respirar, pide ayuda urgente\n"
        f"El dolor o daño físico se clasifica como FÍSICO, no como 'malestar anímico'. "
        f"Ante la duda entre dos niveles, elegí el más bajo — salvo que haya un golpe, caída "
        f"o dolor, donde conviene el más alto (mejor avisar de más que de menos ante lo físico)."
    )


async def clasificar_distress(
    texto_usuario: str,
    chat_id: Optional[int] = None,
) -> tuple[int, str]:
    """
    Agente vigía: llamada LLM separada y especializada que clasifica el nivel
    de angustia del ÚLTIMO mensaje del adulto. Corre en paralelo con la
    conversación (ver handle_message), así no agrega latencia a la respuesta.

    Separado del agente conversador a propósito: pedirle al mismo modelo que
    converse cálido Y se autotaguee con un token estructurado hacía que
    omitiera la clasificación ~65% de las veces. El vigía, sin la carga de
    "ser cálido", clasifica de forma confiable.

    Retorna (nivel 0-3, motivo breve). Ante cualquier fallo retorna (0, "")
    para no bloquear la respuesta ni disparar falsas alarmas.
    """
    nombre = _nombre_adulto_de(chat_id)
    prompt = _prompt_vigia(texto_usuario, nombre)
    modelo = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")
    try:
        async with usage_mod.timed_chat(modelo) as t:
            r = await _chat_create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=40,
                temperature=0.1,
            )
            t.set_usage(r.usage)
        nivel, motivo = parse_distress_classification(r.choices[0].message.content or "")
        log.info(f"[chat_id={chat_id}] Vigía: nivel={nivel} motivo='{motivo}'")
        return nivel, motivo
    except Exception as e:
        log.warning(f"clasificar_distress falló: {e}")
        return 0, ""


async def clasificar_receptividad(
    texto_usuario: str,
    respuesta_bot: str,
    chat_id: Optional[int] = None,
):
    """Background task: detecta tema y receptividad del último intercambio."""
    nombre = _nombre_adulto_de(chat_id)
    prompt = (
        f"Analizá este intercambio y respondé con exactamente dos líneas.\n\n"
        f"{nombre}: {texto_usuario}\n"
        f"Asistente: {respuesta_bot}\n\n"
        f"TEMA: (1-3 palabras que describan el tema principal, ej: 'tango', 'cocina', 'familia'."
        f" Si es saludo o no hay tema claro, escribí 'general')\n"
        f"RECEPTIVIDAD: (una sola palabra: 'alta', 'baja' o 'neutra'.\n"
        f"  alta = {nombre} amplió, preguntó más, se entusiasmó\n"
        f"  baja = {nombre} cortó el tema, respondió con pocas palabras, rechazó la sugerencia\n"
        f"  neutra = intercambio normal sin señal clara)"
    )
    modelo = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")
    try:
        async with usage_mod.timed_chat(modelo) as t:
            r = await _chat_create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=30,
                temperature=0.1,
            )
            t.set_usage(r.usage)
        texto = r.choices[0].message.content.strip()
        tema = receptividad = None
        for linea in texto.splitlines():
            if linea.upper().startswith("TEMA:"):
                tema = linea.split(":", 1)[1].strip().lower()
            elif linea.upper().startswith("RECEPTIVIDAD:"):
                receptividad = linea.split(":", 1)[1].strip().lower()
        if tema and receptividad in ("alta", "baja", "neutra") and tema != "general":
            palabras = len(texto_usuario.split())
            _guardar_receptividad(tema, receptividad, palabras, chat_id=chat_id)
            log.info(f"Receptividad: tema='{tema}' nivel='{receptividad}' palabras={palabras}")
    except Exception as e:
        log.warning(f"clasificar_receptividad falló: {e}")


def _guardar_receptividad(
    tema: str,
    receptividad: str,
    palabras_usuario: int = 0,
    chat_id: Optional[int] = None,
):
    """Agrega entrada al historial de receptividad."""
    path = _receptividad_path(chat_id)
    entradas = load_json(path, default=[])
    entradas.append({
        "tema": tema,
        "receptividad": receptividad,
        "palabras_usuario": palabras_usuario,
        "ts": datetime.now().isoformat(),
    })
    write_json_atomic(path, entradas[-200:])


def _temas_a_evitar(chat_id: Optional[int] = None) -> list[str]:
    """Devuelve temas a evitar por dos criterios:
    1. Receptividad baja en las últimas 48h (sin señal alta que lo contrarreste).
    2. Engagement muy bajo: promedio < 3 palabras del usuario en 2+ días distintos
       en los últimos 7 días — bloqueado por 7 días.
    """
    entradas = load_json(_receptividad_path(chat_id), default=[])
    if not entradas:
        return []

    ahora = datetime.now().timestamp()
    limite_48h = ahora - 48 * 3600
    limite_7d  = ahora - 7 * 24 * 3600

    bajos = set()
    altos = set()
    # Para criterio de engagement bajo: {tema: {dia: [palabras]}}
    engagement: dict[str, dict[str, list[int]]] = {}

    for e in entradas:
        try:
            ts = datetime.fromisoformat(e["ts"])
        except Exception:
            continue
        ts_f = ts.timestamp()
        if ts_f < limite_7d:
            continue
        tema = e["tema"]
        # Criterio 1: baja/alta en 48h
        if ts_f >= limite_48h:
            if e["receptividad"] == "baja":
                bajos.add(tema)
            elif e["receptividad"] == "alta":
                altos.add(tema)
        # Criterio 2: acumular palabras por día para detectar bajo engagement
        dia = ts.strftime("%Y-%m-%d")
        engagement.setdefault(tema, {}).setdefault(dia, []).append(
            e.get("palabras_usuario", 0)
        )

    # Temas con avg < 3 palabras en 2+ días distintos → bloquear 7 días
    bloqueados_engagement = set()
    for tema, dias in engagement.items():
        dias_bajos = sum(
            1 for palabras in dias.values()
            if palabras and (sum(palabras) / len(palabras)) < 3
        )
        if dias_bajos >= 2:
            bloqueados_engagement.add(tema)

    evitar_48h = {t for t in bajos if t not in altos}
    return list(evitar_48h | (bloqueados_engagement - altos))


def _temas_preferidos(chat_id: Optional[int] = None) -> list[str]:
    """Devuelve ranking de temas por engagement (precalculado en stats.json)."""
    stats = load_json(_stats_path(chat_id))
    for dia in sorted(stats.keys(), reverse=True):
        ranking = stats[dia].get("ranking_temas")
        if ranking:
            return ranking[:5]
    return []


# ---------------------------------------------------------------------------
# Contexto del día (actualidad curada + dólar + clima)
# ---------------------------------------------------------------------------
# Un job de madrugada lee Google News, y un LLM cura la lista dejando SOLO
# temas livianos y conversables (deportes, cultura, efemérides, color local),
# filtrando lo angustiante (guerras, tragedias, crímenes, política dura). El
# escudo se aplica una sola vez, acá, sobre la lista del día — no mensaje por
# mensaje. Los temas sirven para responder si el adulto pregunta Y para traer
# actualidad a la charla por iniciativa.

_CONTEXTO_GLOBAL_PATH = BASE_DIR / "contexto_dia.json"


def _contexto_hogar_path(chat_id: Optional[int]) -> Path:
    if chat_id is None:
        return BASE_DIR / "contexto_dia_local.json"
    return hogar_mod.hogar_dir(chat_id) / "contexto_dia.json"


async def _curar_temas(titulares: list[str], ambito: str) -> list[str]:
    """LLM: de titulares crudos, extrae temas livianos y conversables para un
    adulto mayor, filtrando lo angustiante. Devuelve lista de frases cortas."""
    if not titulares:
        return []
    prompt = (
        f"Estos son titulares de hoy ({ambito}). Elegí hasta 6 TEMAS livianos y "
        f"agradables para charlar con una persona mayor: deportes, cultura, "
        f"espectáculos, efemérides, ciencia curiosa, color local, algo positivo.\n"
        f"EXCLUÍ todo lo angustiante o pesado: guerras, muertes, tragedias, "
        f"crímenes, accidentes, política de conflicto, economía alarmante.\n"
        f"Devolvé UNA LÍNEA por tema, empezando con '- '. En lenguaje simple, pero "
        f"CONSERVANDO los datos concretos y accionables del titular: quién juega "
        f"contra quién, día y hora, dónde verlo, nombres propios. Ej: '- Hoy a las "
        f"18 juegan Francia e Inglaterra por el tercer puesto del Mundial' (NO: "
        f"'- Hay partidos del Mundial'). Sin esos datos el tema no sirve.\n"
        f"Si no hay nada liviano, no devuelvas nada.\n\n"
        + "\n".join(f"· {t}" for t in titulares[:25])
    )
    modelo = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")
    try:
        r = await _chat_create(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.3,
        )
        texto = (r.choices[0].message.content or "")
        temas = [ln.strip().lstrip("-•").strip() for ln in texto.splitlines() if ln.strip().startswith("-")]
        return [t for t in temas if t][:6]
    except Exception as e:
        log.warning(f"_curar_temas ({ambito}) falló: {e}")
        return []


async def actualizar_contexto_del_dia(app=None, chat_id: Optional[int] = None):
    """Job de madrugada. Sin chat_id: arma el contexto GLOBAL (temas generales
    curados + dólar) y luego itera cada hogar para su contexto LOCAL (temas de
    su ciudad + clima). Con chat_id: arma solo el contexto local de ese hogar."""
    hoy = datetime.now().strftime("%Y-%m-%d")

    if chat_id is None:
        # Global: temas generales del país + dólar (igual para todos).
        generales = await _curar_temas(await titulares_google_news(), "noticias generales de Argentina")
        dolar = await consultar_dolar()
        write_json_atomic(_CONTEXTO_GLOBAL_PATH, {"fecha": hoy, "temas_generales": generales, "dolar": dolar})
        log.info(f"Contexto global del día: {len(generales)} temas generales")
        for cid in hogar_mod.listar_hogares():
            await actualizar_contexto_del_dia(app, chat_id=cid)
        return

    # Local por hogar: temas de la ciudad + clima.
    ciudad = _ciudad_de(chat_id)
    locales, clima = [], ""
    if ciudad:
        ciudad_corta = ciudad.split(",")[0]
        locales = await _curar_temas(await titulares_google_news(ciudad_corta), f"noticias de {ciudad_corta}")
        clima = await consultar_clima(ciudad)
    write_json_atomic(_contexto_hogar_path(chat_id), {"fecha": hoy, "temas_locales": locales, "clima": clima})
    log.info(f"Contexto local del hogar {chat_id} ({ciudad}): {len(locales)} temas locales")


def _texto_contexto_del_dia(chat_id: Optional[int]) -> str:
    """Arma el bloque de contexto para el prompt: temas generales + locales +
    dólar + clima del día. Solo usa datos de HOY (si están viejos, los ignora)."""
    hoy = datetime.now().strftime("%Y-%m-%d")
    partes = []
    glob = load_json(_CONTEXTO_GLOBAL_PATH, default={})
    if glob.get("fecha") == hoy:
        if glob.get("temas_generales"):
            partes.append("Temas del país: " + "; ".join(glob["temas_generales"]))
        if glob.get("dolar"):
            partes.append(glob["dolar"])
    local = load_json(_contexto_hogar_path(chat_id), default={})
    if local.get("fecha") == hoy:
        if local.get("temas_locales"):
            partes.append("Temas locales: " + "; ".join(local["temas_locales"]))
        if local.get("clima"):
            partes.append(local["clima"])
    return "\n".join(partes)


def _palabras_en_aprendizajes(chat_id: Optional[int] = None) -> set[str]:
    """Palabras largas del bloque Aprendizajes del perfil (para bonus de scoring)."""
    try:
        perfil_path = _perfil_path(chat_id)
        seccion = read_section(perfil_path.read_text(encoding="utf-8"), "Aprendizajes")
        return {p for linea in seccion.splitlines() for p in linea.lower().split() if len(p) > 4}
    except Exception:
        return set()


def _calcular_ranking_temas(chat_id: Optional[int] = None) -> list[str]:
    """Devuelve temas ordenados por score de engagement (últimas 96h)."""
    entradas = load_json(_receptividad_path(chat_id), default=[])
    if not entradas:
        return []

    palabras_perfil = _palabras_en_aprendizajes(chat_id=chat_id)
    limite = datetime.now().timestamp() - 96 * 3600
    temas: dict[str, dict] = {}

    for e in entradas:
        try:
            ts = datetime.fromisoformat(e["ts"]).timestamp()
        except Exception:
            continue
        if ts < limite:
            continue
        t = e["tema"]
        d = temas.setdefault(t, {"turnos": 0, "palabras": [], "alta": 0, "baja": 0})
        d["turnos"] += 1
        d["palabras"].append(e.get("palabras_usuario", 0))
        if e["receptividad"] == "alta":
            d["alta"] += 1
        elif e["receptividad"] == "baja":
            d["baja"] += 1

    def _score(tema: str, d: dict) -> float:
        avg_palabras = sum(d["palabras"]) / len(d["palabras"]) if d["palabras"] else 0
        alta_ratio = d["alta"] / d["turnos"] if d["turnos"] else 0
        bonus = 10 if any(p in tema for p in palabras_perfil) else 0
        return (avg_palabras * 0.4) + (alta_ratio * 30) + (d["turnos"] * 2) + bonus

    return [t for t, _ in sorted(temas.items(), key=lambda x: _score(x[0], x[1]), reverse=True)]


def _actualizar_seccion_perfil(
    seccion: str,
    nuevas_lineas: list[str],
    chat_id: Optional[int] = None,
):
    """Agrega nuevas líneas al inicio de una sección ## en perfil.md."""
    hoy = date.today().strftime("%d/%m/%Y")
    nuevas = "".join(f"{l} ({hoy})\n" for l in nuevas_lineas)
    perfil_path = _perfil_path(chat_id)
    content = perfil_path.read_text(encoding="utf-8")
    patron = rf"## {seccion}\n.*?(?=\n## |\Z)"
    if re.search(patron, content, re.DOTALL):
        content = content.replace(f"## {seccion}\n", f"## {seccion}\n{nuevas}")
    else:
        content = content.rstrip() + f"\n\n## {seccion}\n{nuevas}"
    write_text_atomic(perfil_path, content)

async def analisis_nocturno(app=None, chat_id: Optional[int] = None):
    """Job nocturno: extrae aprendizajes del log del día y detecta patrones de mejora.

    - Si `chat_id` se da, procesa solo ese hogar.
    - Si es None y hay hogares registrados, itera todos.
    - Si es None y no hay hogares (modo legacy / test), usa los paths globales.
    """
    if chat_id is None:
        hogares = hogar_mod.listar_hogares()
        if hogares:
            for cid in hogares:
                await analisis_nocturno(app=app, chat_id=cid)
            return
        # Modo legacy: sin hogares registrados, usar paths globales del módulo.

    nombre = _nombre_adulto_de(chat_id)
    asistente = _nombre_asistente_de(chat_id)
    hoy = date.today().strftime("%Y-%m-%d")
    log_path = _logs_dir(chat_id) / f"{hoy}.md"
    if not log_path.exists():
        log.info(f"analisis_nocturno: sin log del día (chat_id={chat_id}), nada que analizar")
        return

    log_dia = log_path.read_text(encoding="utf-8")
    perfil_actual = _perfil_path(chat_id).read_text(encoding="utf-8")

    aprendizajes_actuales = read_section(perfil_actual, "Aprendizajes") or "(ninguno)"

    # Estadísticas del día para el resumen nocturno
    stats_dia = _stats_del_dia(hoy, chat_id=chat_id)

    prompt = f"""Sos un asistente que analiza conversaciones de {asistente} con {nombre}, una adulta mayor.

--- LOG DEL DÍA ---
{log_dia}

--- APRENDIZAJES YA CONOCIDOS SOBRE {nombre.upper()} ---
{aprendizajes_actuales}

Respondé con exactamente dos secciones.

REGLAS ESTRICTAS para APRENDIZAJES_NUEVOS:
- Comparar cada dato contra los aprendizajes ya conocidos antes de incluirlo
- Si el dato ya está mencionado (aunque con distintas palabras), NO incluirlo
- Solo hechos concretos sobre {nombre}: eventos, salud, familia, gustos, estado de ánimo
- NO incluir observaciones sobre {asistente} ni sobre la conversación en sí
- Si no hay datos genuinamente nuevos, escribir "ninguno"

APRENDIZAJES_NUEVOS:
(máximo 5 líneas, cada una empezando con "- ". Si no hay nada nuevo: "ninguno")

AJUSTES_CONVERSACION:
(patrones problemáticos observados hoy: respuestas cortadas, preguntas innecesarias al final cuando ya respondiste, temas que {nombre} evitó o cambió, confusiones. Sugerí ajustes accionables. Máximo 3 líneas con "- ". Si la conversación estuvo bien: "ninguno")"""

    modelo = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")
    try:
        async with usage_mod.timed_chat(modelo) as t:
            r = await _chat_create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.2,
            )
            t.set_usage(r.usage)
        respuesta = r.choices[0].message.content.strip()
        log.info(f"analisis_nocturno respuesta LLM:\n{respuesta}")

        aprendizajes = _parsear_seccion(respuesta, "APRENDIZAJES_NUEVOS")
        ajustes = _parsear_seccion(respuesta, "AJUSTES_CONVERSACION")

        if aprendizajes:
            _actualizar_seccion_perfil("Aprendizajes", aprendizajes, chat_id=chat_id)
            log.info(f"analisis_nocturno: {len(aprendizajes)} aprendizaje(s) nuevo(s)")
        if ajustes:
            instrucciones = await _ajustes_a_instrucciones(ajustes, asistente)
            instrucciones = _filtrar_instrucciones_medicas(instrucciones)
            _actualizar_seccion_perfil("Ajustes sugeridos", instrucciones, chat_id=chat_id)
            log.info(f"analisis_nocturno: {len(instrucciones)} ajuste(s) convertido(s) a instrucciones")

        # Calcular ranking de engagement por tema y guardarlo en stats
        ranking = _calcular_ranking_temas(chat_id=chat_id)

        # Guardar resumen del día en stats.json
        _actualizar_stats_resumen(hoy, len(aprendizajes), len(ajustes), stats_dia, ranking, chat_id=chat_id)

        # Detectar síntomas persistentes entre sesiones y alertar al familiar
        await _alertar_sintomas_persistentes(app, log_dia, chat_id=chat_id)

        # Monitoreo de calidad del bot (30 reglas gerontológicas)
        alertas = _monitoreo_calidad_bot(log_dia, chat_id=chat_id)
        if alertas:
            log.warning(f"analisis_nocturno calidad [{len(alertas)} alerta(s)]: {alertas}")

        # Inyectar temática activa si se repite en sesiones consecutivas (RULE_MEM_01)
        _inyectar_tematica_activa(chat_id=chat_id)

    except Exception as e:
        log.warning(f"analisis_nocturno falló: {e}")

_SINTOMAS_KEYWORDS = re.compile(
    r"\b(dolor|duele|duelen|ojos rojos|muela|rodilla|espalda|cabeza|presión|"
    r"mareo|mareos|náuseas|cansada|caída|caí|no pude dormir|insomnio)\b",
    re.IGNORECASE,
)

async def _alertar_sintomas_persistentes(app, log_hoy: str, chat_id: Optional[int] = None):
    """Si un síntoma aparece hoy Y en el log de ayer, alerta al familiar silenciosamente."""
    try:
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        log_ayer_path = _logs_dir(chat_id) / f"{ayer}.md"
        if not log_ayer_path.exists():
            return

        sintomas_hoy  = set(_SINTOMAS_KEYWORDS.findall(log_hoy.lower()))
        sintomas_ayer = set(_SINTOMAS_KEYWORDS.findall(log_ayer_path.read_text(encoding="utf-8").lower()))
        persistentes  = sintomas_hoy & sintomas_ayer
        if not persistentes:
            return

        nombre = _nombre_adulto_de(chat_id)
        texto = (
            f"🩺 *Síntoma(s) persistente(s) en {nombre}*\n\n"
            f"Los siguientes síntomas aparecieron tanto ayer como hoy:\n"
            f"{', '.join(sorted(persistentes))}\n\n"
            f"No es una emergencia, pero puede valer la pena consultar al médico "
            f"si {nombre} no lo mencionó en su última visita."
        )
        family_bot = app.bot_data.get("family_bot") if app else None
        if not family_bot:
            log.info(f"Síntomas persistentes detectados ({persistentes}) pero family_bot no configurado")
            return
        from core.alerts import cargar_suscriptores
        suscriptores = (
            cargar_suscriptores(chat_id) if chat_id is not None
            else cargar_suscriptores()
        )
        for fam_chat_id in suscriptores:
            try:
                await family_bot.send_message(chat_id=fam_chat_id, text=texto, parse_mode="Markdown")
            except Exception as e:
                log.warning(f"No se pudo enviar alerta de síntomas a {fam_chat_id}: {e}")
        log.info(f"Alerta de síntomas persistentes enviada: {persistentes}")
    except Exception as e:
        log.warning(f"_alertar_sintomas_persistentes falló: {e}")


_VERBOS_INDAGACION_MEDICA = re.compile(
    r"\b(pregunt[ae]|averiguá|indagá|consultá|preguntale)\b.{0,60}"
    r"(dolor|duele|síntoma|síntomas|salud|médico|remedio|pastilla|gota|ojo|ojos|muela|"
    r"rodilla|espalda|cabeza|presión|colesterol|medicación|medicamento)",
    re.IGNORECASE,
)

def _filtrar_instrucciones_medicas(instrucciones: list[str]) -> list[str]:
    """Elimina instrucciones que le piden a Aikiu indagar en síntomas al día siguiente."""
    filtradas = [i for i in instrucciones if not _VERBOS_INDAGACION_MEDICA.search(i)]
    removidas = len(instrucciones) - len(filtradas)
    if removidas:
        log.info(f"analisis_nocturno: {removidas} instrucción(es) médica(s) filtrada(s)")
    return filtradas


_RE_PREGUNTA_CIERRE   = re.compile(r"\?[\"']?\s*$", re.MULTILINE)
_RE_TRUNCADO          = re.compile(r"(?<![.!?\"'])\s*$")
_RE_MARKDOWN          = re.compile(r"[*\-#_\[\]|`]")
_RE_CHE_CIERRE        = re.compile(r",?\s*che\s*\?", re.IGNORECASE)
_RE_OVERLAP_STOP      = {"de", "la", "el", "los", "las", "un", "una", "que", "y", "en", "a", "con"}
_RE_SOLEDAD_FAMILIAR  = re.compile(r"\b(germán|lao|cata|familia)\b", re.IGNORECASE)
_RE_SOLEDAD_TRIGGER   = re.compile(r"\b(silencio|sola|soledad|nadie)\b", re.IGNORECASE)
_RE_CTRL_AUTOCUIDADO  = re.compile(r"¿pudiste\s+(tomar|descansar|poner|comer|dormir)", re.IGNORECASE)
_RE_EDAD_DOLOR        = re.compile(r"\b(edad|envejecer|mayor|vieja|costumbre).{0,40}(dolor|duele|normal)\b", re.IGNORECASE)
_RE_EXCLAMACION_BOT   = re.compile(r"¡[^!]{0,40}!")
_RE_FARMACO           = re.compile(r"\b(efectividad|te ayud[oó]|dosis|tomar(la|las)|horario).{0,30}(gota|remedio|pastilla|medicamento)\b", re.IGNORECASE)


def _monitoreo_calidad_bot(log_dia: str, chat_id: Optional[int] = None) -> list[str]:
    """RULE_VUI_02 a RULE_CTRL_29: detecta patrones de baja calidad en los logs del día.

    En multi-tenant, los nombres del adulto y de la asistente vienen de la vista
    del hogar (`chat_id`). Si no se pasa `chat_id`, se cae a CONFIG global."""
    alertas = []
    if chat_id is None:
        nombre    = CONFIG["nombre_adulto_mayor"]
        asistente = CONFIG["nombre_asistente"]
    else:
        nombre    = _nombre_adulto_de(chat_id)
        asistente = _nombre_asistente_de(chat_id)

    turnos_bot = re.findall(rf"- {asistente}: (.+)", log_dia)
    turnos_usr = re.findall(rf"- {nombre}: (.+)", log_dia)
    if not turnos_bot:
        return alertas

    # RULE_VUI_02: ratio de preguntas > 50%
    con_pregunta = sum(1 for t in turnos_bot if _RE_PREGUNTA_CIERRE.search(t))
    if turnos_bot and con_pregunta / len(turnos_bot) > 0.5:
        alertas.append(f"RULE_VUI_02: interrogatorio ({con_pregunta}/{len(turnos_bot)} turnos con pregunta)")

    # RULE_ERR_03: respuestas truncadas (no terminan en puntuación de cierre)
    truncados = [t for t in turnos_bot if _RE_TRUNCADO.search(t) and not re.search(r"[.!?]$", t.strip())]
    if truncados:
        alertas.append(f"RULE_ERR_03: {len(truncados)} respuesta(s) truncada(s)")

    # RULE_LEX_04: solapamiento léxico > 40% entre turno usuario y turno bot
    solapamientos = 0
    for u, b in zip(turnos_usr, turnos_bot):
        palabras_u = {w.lower() for w in re.findall(r"\w{4,}", u)} - _RE_OVERLAP_STOP
        palabras_b = {w.lower() for w in re.findall(r"\w{4,}", b)} - _RE_OVERLAP_STOP
        if palabras_u and len(palabras_u & palabras_b) / len(palabras_u) > 0.4:
            solapamientos += 1
    if solapamientos:
        alertas.append(f"RULE_LEX_04: eco léxico en {solapamientos} turno(s)")

    # RULE_LIN_10: "che" como sufijo de pregunta
    che_mal = sum(1 for t in turnos_bot if _RE_CHE_CIERRE.search(t))
    if che_mal:
        alertas.append(f"RULE_LIN_10: 'che' al cierre de pregunta en {che_mal} turno(s)")

    # RULE_TON_13: exclamaciones ante tono neutro/negativo del usuario
    _NEGATIVO = re.compile(r"\b(sola|cansada|triste|mal|duele|silencio|extraño|pobrecita)\b", re.IGNORECASE)
    for u, b in zip(turnos_usr, turnos_bot):
        if _NEGATIVO.search(u) and _RE_EXCLAMACION_BOT.search(b):
            alertas.append("RULE_TON_13: exclamación ante tono negativo del usuario")
            break

    # RULE_LON_19: listar familiares como respuesta a soledad
    for u, b in zip(turnos_usr, turnos_bot):
        if _RE_SOLEDAD_TRIGGER.search(u) and _RE_SOLEDAD_FAMILIAR.search(b):
            alertas.append("RULE_LON_19: enumeración de familiares ante soledad declarada")
            break

    # RULE_GER_08: edadismo (dolor asociado a vejez)
    for t in turnos_bot:
        if _RE_EDAD_DOLOR.search(t):
            alertas.append("RULE_GER_08: sesgo edadista detectado")
            break

    # RULE_TXT_24: markdown en output del bot
    md_turnos = sum(1 for t in turnos_bot if _RE_MARKDOWN.search(t))
    if md_turnos:
        alertas.append(f"RULE_TXT_24: markdown en {md_turnos} turno(s) del bot")

    # RULE_MED_06: preguntas sobre efectividad de medicamentos
    for t in turnos_bot:
        if _RE_FARMACO.search(t):
            alertas.append("RULE_MED_06: pregunta sobre efectividad de fármaco")
            break

    # RULE_CTRL_29: preguntas de control de autocuidado
    ctrl = sum(1 for t in turnos_bot if _RE_CTRL_AUTOCUIDADO.search(t))
    if ctrl:
        alertas.append(f"RULE_CTRL_29: {ctrl} pregunta(s) de control de autocuidado")

    # RULE_CLOSE_30: última respuesta del bot termina con pregunta
    if turnos_bot and _RE_PREGUNTA_CIERRE.search(turnos_bot[-1]):
        alertas.append("RULE_CLOSE_30: sesión cerrada con repregunta abierta")

    return alertas


_TEMATICA_ACTIVA_PATH = BASE_DIR / "tematica_activa.json"


def _tematica_activa_path(chat_id: Optional[int]) -> Path:
    """Path per-hogar del archivo `tematica_activa.json` (multi-tenant).
    Si `chat_id` es None se cae al path legacy global (compat con tests
    single-tenant)."""
    if chat_id is None:
        return _TEMATICA_ACTIVA_PATH
    return hogar_mod.hogar_dir(chat_id) / "tematica_activa.json"


def _inyectar_tematica_activa(chat_id: Optional[int] = None):
    """RULE_MEM_01: si el mismo tema de alegría aparece en 2+ sesiones consecutivas,
    registrarlo para que el bot use verbos de continuidad al día siguiente."""
    try:
        entradas = load_json(_receptividad_path(chat_id), default=[])
        ahora = datetime.now()
        ayer   = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")
        hoy    = ahora.strftime("%Y-%m-%d")

        temas_alta_hoy  = {e["tema"] for e in entradas if e["receptividad"] == "alta" and e["ts"][:10] == hoy}
        temas_alta_ayer = {e["tema"] for e in entradas if e["receptividad"] == "alta" and e["ts"][:10] == ayer}
        activos = list(temas_alta_hoy & temas_alta_ayer)

        data = {"temas": activos, "ts": ahora.isoformat()}
        destino = _tematica_activa_path(chat_id)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if activos:
            log.info(f"RULE_MEM_01: temática activa detectada → {activos}")
    except Exception as e:
        log.warning(f"_inyectar_tematica_activa falló: {e}")


async def _ajustes_a_instrucciones(ajustes: list[str], asistente: str) -> list[str]:
    """Convierte ajustes descriptivos en instrucciones imperativas para el system prompt."""
    if not ajustes:
        return []
    lista = "\n".join(ajustes)
    prompt = (
        f"Convertí cada observación en una instrucción directa e imperativa para {asistente}, "
        f"un asistente de voz. Sin explicaciones, solo la instrucción. "
        f"Una línea por ítem, empezando con '- '. Observaciones:\n{lista}"
    )
    modelo = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")
    try:
        async with usage_mod.timed_chat(modelo) as t:
            r = await _chat_create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.1,
            )
            t.set_usage(r.usage)
        resultado = r.choices[0].message.content.strip()
        instrucciones = [l.strip() for l in resultado.splitlines() if l.strip().startswith("-")]
        return instrucciones if instrucciones else ajustes
    except Exception as e:
        log.warning(f"_ajustes_a_instrucciones falló: {e}")
        return ajustes  # fallback: guardar los originales


def _stats_del_dia(hoy: str, chat_id: Optional[int] = None) -> dict:
    """Devuelve las stats acumuladas del día o un dict vacío."""
    return load_json(_stats_path(chat_id)).get(hoy, {})

def _actualizar_stats_resumen(
    hoy: str,
    n_aprendizajes: int,
    n_ajustes: int,
    stats_dia: dict,
    ranking: list[str] | None = None,
    chat_id: Optional[int] = None,
):
    """Agrega al stats del día el resumen del análisis nocturno."""
    path = _stats_path(chat_id)
    stats = load_json(path)
    dia = stats.setdefault(hoy, stats_dia or {})
    dia["analisis_nocturno"] = {
        "aprendizajes_nuevos": n_aprendizajes,
        "ajustes_sugeridos": n_ajustes,
    }
    if ranking:
        dia["ranking_temas"] = ranking
    write_json_atomic(path, stats)
    log.info(f"analisis_nocturno: stats actualizadas para {hoy} (chat_id={chat_id})")


def _parsear_seccion(texto: str, seccion: str) -> list[str]:
    """Extrae líneas con '- ' de una sección del output del LLM.
    Tolera variantes: 'SECCION:', '## SECCION', 'SECCION\n'.
    """
    patron = rf"(?:##\s*)?{seccion}[:\n](.*?)(?=\n(?:##\s*)?[A-Z_]{{3,}}[:\n]|\Z)"
    m = re.search(patron, texto, re.DOTALL)
    if not m:
        return []
    bloque = m.group(1).strip()
    lineas = [l.strip() for l in bloque.splitlines() if l.strip().startswith("-")]
    # Filtrar líneas que contengan "ninguno" (respuesta fallback del LLM)
    lineas = [l for l in lineas if "ninguno" not in l.lower()]
    if not lineas and "ninguno" in bloque.lower():
        return []
    return lineas

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat_id_autorizado(chat_id: int) -> bool:
    """En multi-tenant TODO chat_id puede operar: si no tiene hogar todavía,
    se lo crea en `handle_message`/`cmd_start`. La función se mantiene como
    extension point para futuros bloqueos (ban, lista negra)."""
    return True


def _owner_chat_id_o_warn() -> int | None:
    """Compat: devuelve el primer hogar registrado o None.

    Solo usado por código legacy que asume un único hogar. El flujo
    multi-tenant maneja chat_ids explícitos.
    """
    cid = state_mod.owner_chat_id()
    if cid is None:
        hogares = hogar_mod.listar_hogares()
        if hogares:
            return hogares[0]
        log.warning(
            "No hay adultos registrados todavía: cualquier /start al bot va a "
            "crear el primer hogar automáticamente."
        )
    return cid

async def responder_con_voz(context, chat_id: int, texto: str):
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "respuesta.ogg"
        await sintetizar(texto, ogg, voz=_voz_tts_de(chat_id))
        with open(ogg, "rb") as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_invitar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera un código de invitación de 6 caracteres para compartir con
    un familiar. El familiar lo usa con `/vincular <CODIGO>` en el bot
    familiar y queda asociado a este hogar."""
    chat_id = update.effective_chat.id
    raw_first = getattr(update.effective_user, "first_name", None) if update.effective_user else None
    nombre_tg = raw_first if isinstance(raw_first, str) and raw_first else None
    _asegurar_hogar(chat_id, nombre_tg=nombre_tg)

    try:
        codigo = invites_mod.generar_codigo(chat_id)
    except Exception as e:
        log.warning(f"cmd_invitar falló: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="No pude generar el código. Intentá de nuevo en un rato."
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"Listo. Pasale este código a tu familiar:\n\n"
            f"*{codigo}*\n\n"
            f"Tiene que escribir en el bot familiar:\n"
            f"`/vincular {codigo}`\n\n"
            f"_Vale por 24 horas y un solo uso._"
        ),
        parse_mode="Markdown",
    )


import configurar as configurar_mod
from telegram.ext import ConversationHandler

# Estados del wizard de onboarding del adulto en el bot principal.
# Se preguntan en cadena en el primer /start del adulto. Cada respuesta
# se persiste en `state.json` bajo `onboarding_progress` por si el chat
# se cierra a mitad del wizard (al volver con /start, se reanuda).
(
    OB_NOMBRE, OB_EDAD, OB_CIUDAD, OB_FAMILIA, OB_GUSTOS,
) = range(5)

_OB_PASOS = ("nombre", "edad", "ciudad", "familiares", "gustos")
_OB_NO_RESPUESTAS = {"no", "no se", "no sé", "ninguno", "ninguna", "nada", "no recuerdo"}


async def _texto_desde_update(update: Update) -> str:
    """Extrae el texto del mensaje, transcribiendo si es voz. '' si no hay nada."""
    msg = update.message
    if msg is None:
        return ""
    if msg.voice:
        with tempfile.TemporaryDirectory() as tmp:
            ogg = Path(tmp) / "entrada.ogg"
            file = await msg.voice.get_file()
            await file.download_to_drive(ogg)
            texto = await transcribir(ogg)
        return (texto or "").strip()
    return (msg.text or "").strip()


# Saludos y frases de presentación que la gente antepone al nombre,
# sobre todo hablando (voz): "hola, soy Marta", "me llamo Juan Carlos".
_OB_NOMBRE_PREFIJOS = re.compile(
    r"^\s*(hola|buenas|buen[oa]s?\s+d[ií]as?|buen\s+d[ií]a|buenas\s+tardes|buenas\s+noches|"
    r"che|holis|qu[eé]\s+tal|me\s+llamo|mi\s+nombre\s+es|yo\s+soy|soy|me\s+dicen)\b[\s,.:]*",
    re.IGNORECASE,
)


def _extraer_nombre(texto: str) -> str:
    """Extrae el nombre de una respuesta conversacional.

    'hola, soy german' → 'German'; 'me llamo maría josé' → 'María José'.
    Saca saludos/presentaciones del inicio y se queda con las primeras
    palabras (nombres compuestos), capitalizadas. Si no queda nada, "".
    """
    t = (texto or "").strip()
    prev = None
    while prev != t:
        prev = t
        t = _OB_NOMBRE_PREFIJOS.sub("", t, count=1).strip()
    t = re.split(r"[,.\n;]", t)[0].strip()  # cortar en la primera cláusula
    palabras = t.split()[:3]                # nombre + hasta 2 (compuestos)
    return " ".join(w.capitalize() for w in palabras)


# Nombres comunes que la heurística por terminación no acierta.
_GENERO_OVERRIDE = {
    "german": "M", "germán": "M", "juan": "M", "matías": "M", "matias": "M",
    "tomás": "M", "tomas": "M", "andrés": "M", "andres": "M", "nicolás": "M",
    "nicolas": "M", "joaquín": "M", "joaquin": "M", "agustín": "M", "agustin": "M",
    "carmen": "F", "rosario": "F", "pilar": "F", "beatriz": "F", "isabel": "F",
    "mercedes": "F", "dolores": "F", "soledad": "F", "raquel": "F",
}


def _inferir_genero(nombre: str) -> str:
    """Infiere 'M' o 'F' del nombre. Heurística rioplatense: termina en 'a' → F,
    en 'o' → M; con overrides para nombres comunes que no siguen la regla.
    Default 'F' (la base de usuarios tiende a mujeres mayores). Editable a mano."""
    if not nombre:
        return "F"
    primero = norm(nombre.split()[0])  # sin acentos, lower
    if primero in _GENERO_OVERRIDE:
        return _GENERO_OVERRIDE[primero]
    if primero.endswith("a"):
        return "F"
    if primero.endswith("o"):
        return "M"
    return "F"


def _genero_de(chat_id: Optional[int]) -> str:
    """Género del adulto ('M'/'F') para adaptar el trato. Default 'F'."""
    if chat_id is None:
        return CONFIG.get("genero", "F") or "F"
    return _config_hogar(chat_id).get("genero", "F") or "F"


def _normalizar_respuesta_onboarding(valor: str, paso: str) -> str | list[str]:
    """Devuelve el valor a guardar para `paso` dada la respuesta `valor`.

    - "no", "no sé", "nada" → vacío (campo opcional saltado).
    - `familiares` y `gustos` se parsean como lista (líneas o comas).
    - `nombre` → se extrae de la frase (saca "hola, soy...").
    - resto → string strippeado.
    """
    if not valor or norm(valor) in _OB_NO_RESPUESTAS:
        if paso in ("familiares", "gustos"):
            return []
        return ""
    if paso in ("familiares", "gustos"):
        items: list[str] = []
        for raw in re.split(r"[\n,]", valor):
            item = raw.strip().lstrip("-•").strip()
            if item:
                items.append(item)
        return items
    if paso == "nombre":
        return _extraer_nombre(valor)
    return valor.strip()


_OB_PROMPTS = {
    OB_NOMBRE: ("1/5 ¿Cómo te llamás? (Solo el nombre está bien)"),
    OB_EDAD: ("2/5 ¿Cuántos años tenés? (Podés decir 'no sé' para saltar)"),
    OB_CIUDAD: ("3/5 ¿En qué ciudad vivís?"),
    OB_FAMILIA: (
        "4/5 ¿Quiénes son tus familiares más cercanos? Nombrámelos en una "
        "frase. Por ejemplo: 'mi hija Laura y mi nieto Juan'."
    ),
    OB_GUSTOS: (
        "5/5 ¿Qué te gusta hacer o sobre qué te gusta hablar? Por ejemplo: "
        "'tango, cocinar, las plantas'."
    ),
}


def _onboarding_pendiente(estado: dict) -> bool:
    """True si el hogar todavía no completó el wizard de bienvenida."""
    if estado.get("perfil_completo"):
        return False
    return True


def _proximo_paso_onboarding(estado: dict) -> int:
    """Estado siguiente del ConversationHandler según `onboarding_progress`."""
    progreso = estado.get("onboarding_progress", {}) or {}
    for idx, clave in enumerate(_OB_PASOS):
        if clave not in progreso:
            return [OB_NOMBRE, OB_EDAD, OB_CIUDAD, OB_FAMILIA, OB_GUSTOS][idx]
    return OB_NOMBRE  # ya completó todo pero perfil_completo no marcó: arrancar de cero


def _guardar_progreso_ob(chat_id: int, paso: str, valor) -> dict:
    estado = hogar_mod.leer_state(chat_id) or {"owner_chat_id": int(chat_id)}
    progreso = dict(estado.get("onboarding_progress") or {})
    progreso[paso] = valor
    estado["onboarding_progress"] = progreso
    hogar_mod.escribir_state(chat_id, estado)
    return estado


def _finalizar_onboarding(chat_id: int) -> tuple[Path, str]:
    """Escribe `perfil.md` con las respuestas y marca `perfil_completo: true`.

    Devuelve (path_perfil, nombre_del_adulto)."""
    estado = hogar_mod.leer_state(chat_id) or {"owner_chat_id": int(chat_id)}
    progreso = estado.get("onboarding_progress") or {}
    nombre = (progreso.get("nombre") or estado.get("nombre_adulto") or "").strip()

    datos = {
        "nombre": nombre,
        "edad": progreso.get("edad", ""),
        "ciudad": progreso.get("ciudad", ""),
        "descripcion": "",
        "nombre_asistente": estado.get("nombre_asistente") or CONFIG.get("nombre_asistente", "Aikiu"),
        "familiares": progreso.get("familiares") or [],
        "gustos": progreso.get("gustos") or [],
        "salud": [],
    }

    perfil_md = configurar_mod.generar_perfil(datos)
    perfil_path = hogar_mod.perfil_path(chat_id)
    perfil_path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(perfil_path, perfil_md)

    if nombre:
        estado["nombre_adulto_mayor"] = nombre
        # Inferir género del nombre para adaptar el trato (editable a mano).
        # No se pisa si ya venía seteado (ej. corregido por la familia).
        estado.setdefault("genero", _inferir_genero(nombre))
    if datos["ciudad"]:
        estado["ciudad"] = datos["ciudad"]
    estado["perfil_completo"] = True
    hogar_mod.escribir_state(chat_id, estado)
    return perfil_path, nombre


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Self-service onboarding: cualquier chat_id que mande /start crea su hogar.

    Si el hogar es nuevo o tiene onboarding pendiente, arranca el wizard
    (devuelve un estado del ConversationHandler). Si el adulto ya está
    onboardeado, manda solo el saludo y termina (END)."""
    chat_id = update.effective_chat.id
    raw_first = getattr(update.effective_user, "first_name", None) if update.effective_user else None
    nombre_tg = raw_first if isinstance(raw_first, str) and raw_first else None

    nuevo = _asegurar_hogar(chat_id, nombre_tg=nombre_tg)
    estado = hogar_mod.leer_state(chat_id) or {}
    asistente = _nombre_asistente_de(chat_id) or "Aikiu"

    if _onboarding_pendiente(estado):
        nombre_visible = nombre_tg or _nombre_adulto_de(chat_id) or ""
        saludo = nombre_visible and f"Hola {nombre_visible}." or "Hola."
        intro = (
            f"{saludo} Soy {asistente}. "
            f"Antes de empezar te hago unas preguntas cortas para conocerte "
            f"mejor. Podés contestarme por texto o por voz, lo que te resulte "
            f"más cómodo. Si alguna pregunta no querés contestar, decime 'no' "
            f"o mandá /saltar. Para abandonar el cuestionario, /cancelar.\n\n"
        )
        siguiente = _proximo_paso_onboarding(estado)
        await context.bot.send_message(chat_id=chat_id, text=intro + _OB_PROMPTS[siguiente])
        if nuevo:
            log.info(f"[ONBOARDING] arrancando wizard para chat_id={chat_id}")
        return siguiente

    nombre = _nombre_adulto_de(chat_id) or nombre_tg or ""
    if nombre:
        bienvenida = f"Hola {nombre}, soy {asistente}. ¿En qué te puedo ayudar?"
    else:
        bienvenida = f"Hola, soy {asistente}. ¿En qué te puedo ayudar?"
    await context.bot.send_message(chat_id=chat_id, text=bienvenida)
    return ConversationHandler.END


async def _ob_recibir(update: Update, context: ContextTypes.DEFAULT_TYPE, paso: str, siguiente_estado: int | None):
    """Handler genérico de cada paso. Persiste el progreso y avanza."""
    chat_id = update.effective_chat.id
    texto = await _texto_desde_update(update)
    valor = _normalizar_respuesta_onboarding(texto, paso)

    if paso == "nombre" and not valor:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Necesito al menos tu nombre para llamarte. ¿Cómo te llamás?",
        )
        return OB_NOMBRE

    _guardar_progreso_ob(chat_id, paso, valor)

    if siguiente_estado is None:
        perfil_path, nombre = _finalizar_onboarding(chat_id)
        log.info(f"[ONBOARDING] completado chat_id={chat_id} → {perfil_path}")
        asistente = _nombre_asistente_de(chat_id) or "Aikiu"
        cierre = (
            f"Listo{', ' + nombre if nombre else ''}. Ya está. "
            f"Soy {asistente} y voy a estar acá cuando me necesites. "
            f"Contame cómo estás hoy o pedime lo que quieras."
        )
        await context.bot.send_message(chat_id=chat_id, text=cierre)
        return ConversationHandler.END

    await context.bot.send_message(chat_id=chat_id, text=_OB_PROMPTS[siguiente_estado])
    return siguiente_estado


async def ob_nombre(update, context):
    return await _ob_recibir(update, context, "nombre", OB_EDAD)


async def ob_edad(update, context):
    return await _ob_recibir(update, context, "edad", OB_CIUDAD)


async def ob_ciudad(update, context):
    return await _ob_recibir(update, context, "ciudad", OB_FAMILIA)


async def ob_familia(update, context):
    return await _ob_recibir(update, context, "familiares", OB_GUSTOS)


async def ob_gustos(update, context):
    return await _ob_recibir(update, context, "gustos", None)


async def cmd_saltar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Salta la pregunta actual con valor vacío y avanza al siguiente paso."""
    chat_id = update.effective_chat.id
    estado = hogar_mod.leer_state(chat_id) or {}
    siguiente = _proximo_paso_onboarding(estado)
    paso_actual = _OB_PASOS[siguiente]  # el paso que está pendiente AHORA
    if paso_actual == "nombre":
        await context.bot.send_message(
            chat_id=chat_id,
            text="El nombre no se puede saltar. ¿Cómo te llamás?",
        )
        return OB_NOMBRE
    valor: str | list[str] = [] if paso_actual in ("familiares", "gustos") else ""
    _guardar_progreso_ob(chat_id, paso_actual, valor)
    # Buscar el siguiente paso después de saltear
    estado = hogar_mod.leer_state(chat_id)
    idx_actual = _OB_PASOS.index(paso_actual)
    if idx_actual + 1 >= len(_OB_PASOS):
        perfil_path, nombre = _finalizar_onboarding(chat_id)
        log.info(f"[ONBOARDING] completado tras /saltar chat_id={chat_id} → {perfil_path}")
        asistente = _nombre_asistente_de(chat_id) or "Aikiu"
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"Listo{', ' + nombre if nombre else ''}. Ya está. "
                f"Soy {asistente} y voy a estar acá cuando me necesites."
            ),
        )
        return ConversationHandler.END
    nuevo_estado = [OB_NOMBRE, OB_EDAD, OB_CIUDAD, OB_FAMILIA, OB_GUSTOS][idx_actual + 1]
    await context.bot.send_message(chat_id=chat_id, text=_OB_PROMPTS[nuevo_estado])
    return nuevo_estado


async def cmd_cancelar_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aborta el wizard. El perfil queda neutro hasta que vuelva /start o
    el familiar use /configurar."""
    chat_id = update.effective_chat.id
    asistente = _nombre_asistente_de(chat_id) or "Aikiu"
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"Listo, dejamos las preguntas para otro momento. "
            f"Soy {asistente}, podés escribirme cuando quieras."
        ),
    )
    return ConversationHandler.END

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Error handler global. Ante cualquier excepción no atrapada en un handler,
    lo registra y le manda al adulto una frase cálida en vez de dejarlo en
    silencio. El silencio mata la confianza más que una respuesta imperfecta."""
    log.error("Excepción no atrapada en un handler", exc_info=context.error)
    try:
        chat_id = getattr(getattr(update, "effective_chat", None), "id", None)
        if chat_id is not None:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Uy, se me cruzaron los cables un segundo. ¿Me lo repetís?",
            )
    except Exception as e:
        log.warning(f"on_error no pudo avisar al usuario: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not chat_id_autorizado(chat_id):
        log.warning(f"chat_id no autorizado: {chat_id}")
        return

    # Self-service: si el chat_id es nuevo, lo damos de alta sin pedir /start.
    raw_first = getattr(update.effective_user, "first_name", None) if update.effective_user else None
    nombre_tg = raw_first if isinstance(raw_first, str) and raw_first else None
    _asegurar_hogar(chat_id, nombre_tg=nombre_tg)

    is_voice = bool(update.message.voice)
    action = "record_voice" if is_voice else "typing"
    await context.bot.send_chat_action(chat_id=chat_id, action=action)

    # Obtener texto — voz o texto plano
    if is_voice:
        with tempfile.TemporaryDirectory() as tmp:
            ogg = Path(tmp) / "entrada.ogg"
            file = await update.message.voice.get_file()
            await file.download_to_drive(ogg)
            texto = await transcribir(ogg)
        if not texto:
            await responder_con_voz(context, chat_id, "No te escuché bien, ¿podés repetir?")
            return
    else:
        texto = update.message.text.strip()

    # Camino de la respuesta: SOLO el conversador. El vigía (clasificación de
    # angustia) NO va acá — corría en paralelo pero las dos llamadas a
    # OpenRouter se peleaban y sumaban ~12s. Ahora el vigía corre en background
    # después de responder, así el usuario espera solo una llamada.
    historial = _get_historial(chat_id)
    raw = await generar_respuesta(texto, historial, chat_id=chat_id)
    # parse_llm_response limpia cualquier línea DISTRESS residual que el
    # conversador pudiera emitir (el nivel real lo pone el vigía en background).
    respuesta, _ = parse_llm_response(raw)
    log.info(f"[chat_id={chat_id}] LLM: '{respuesta}'")

    historial.append({"role": "user",      "content": texto})
    historial.append({"role": "assistant", "content": respuesta})
    _persistir_historial(chat_id, historial)  # sobrevive a reinicios, podado

    # Responde en voz solo si el hogar prefiere voz Y el mensaje entró por voz.
    # Con preferencia 'texto' (default mientras iteramos), siempre texto —
    # aunque le hablen — para esquivar el TTS metálico de edge-tts.
    if is_voice and _medio_de(chat_id) == "voz":
        await responder_con_voz(context, chat_id, respuesta)
    else:
        await context.bot.send_message(chat_id=chat_id, text=respuesta)

    # Registrar actividad para el sistema de inactividad (por hogar)
    _ultimas_actividades[chat_id] = datetime.now()
    # Backwards compat: mantener el global para tests viejos que lo inspeccionan.
    global _ultima_actividad
    _ultima_actividad = datetime.now()

    # Vigía + alerta + stats: todo en background, sin bloquear la respuesta.
    family_bot = context.bot_data.get("family_bot")
    create_background_task(
        _evaluar_distress_y_extras(texto, respuesta, chat_id, family_bot)
    )


async def _evaluar_distress_y_extras(texto, respuesta, chat_id, family_bot):
    """Corre el vigía (clasificación de angustia), dispara la alerta si
    corresponde, y registra stats/log/receptividad. Todo en background: nada
    de esto bloquea la respuesta al usuario. La alerta es lo prioritario."""
    distress_level, distress_motivo = await clasificar_distress(texto, chat_id=chat_id)

    # Alerta de seguridad PRIMERO — antes que las tareas cosméticas.
    if should_send_alert(distress_level, adulto_chat_id=chat_id):
        record_alert_sent(distress_level, adulto_chat_id=chat_id)
        if family_bot:
            log.info(f"Enviando alerta nivel {distress_level} a suscriptores del hogar {chat_id}")
            await notify_family(
                distress_level=distress_level,
                adulto_message=texto,
                bot_response=respuesta,
                family_bot=family_bot,
                adulto_chat_id=chat_id,
                motivo=distress_motivo,
            )
        else:
            log.warning("Alerta detectada pero family_bot no está configurado — revisar FAMILIAR_BOT_TOKEN en .env")

    # Tareas cosméticas — blindadas: un fallo acá no afecta la alerta.
    try:
        registrar_log(texto, respuesta, chat_id=chat_id)
        registrar_stats(distress_level, chat_id=chat_id)
        await clasificar_receptividad(texto, respuesta, chat_id=chat_id)
    except Exception as e:
        log.warning(f"Tarea cosmética falló (no afecta la alerta): {e}")

# ---------------------------------------------------------------------------
# Mensajes proactivos
# ---------------------------------------------------------------------------

async def enviar_mensaje_voz(
    app: Application,
    texto: str,
    chat_id: Optional[int] = None,
):
    """
    Envía una nota de voz proactiva.

    - Si `chat_id` se especifica, manda a ese hogar.
    - Si es None, busca todos los hogares registrados y manda a cada uno
      (modo multi-tenant). Si no hay hogares, intenta el `owner_chat_id`
      legacy para preservar comportamiento viejo.
    """
    if chat_id is None:
        hogares = hogar_mod.listar_hogares()
        if hogares:
            for cid in hogares:
                await enviar_mensaje_voz(app, texto, chat_id=cid)
            return
        # Legacy fallback
        chat_id = _owner_chat_id_o_warn()
        if chat_id is None:
            log.warning(f"Proactivo NO enviado (sin adulto registrado): '{texto}'")
            return

    # Texto-primero: mientras iteramos la calidad conversacional, los mensajes
    # proactivos van en texto salvo que el hogar pida voz explícitamente. La
    # voz de edge-tts suena metálica; se retoma cuando haya un TTS mejor.
    if _medio_de(chat_id) == "texto":
        await app.bot.send_message(chat_id=chat_id, text=texto)
        log.info(f"Proactivo (texto) enviado a chat_id={chat_id}: '{texto}'")
        return

    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "proactivo.ogg"
        await sintetizar(texto, ogg, voz=_voz_tts_de(chat_id))
        with open(ogg, "rb") as audio:
            await app.bot.send_voice(chat_id=chat_id, voice=audio)
    log.info(f"Proactivo enviado a chat_id={chat_id}: '{texto}'")


async def consultar_feriado(fecha: datetime | None = None) -> str:
    """Devuelve el nombre del feriado argentino si hoy es feriado, o cadena vacía."""
    fecha = fecha or datetime.now()
    hoy = fecha.date().isoformat()
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            r = await client.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{fecha.year}/AR"
            )
            r.raise_for_status()
        for f in r.json():
            if f.get("date") == hoy:
                return f.get("localName") or f.get("name", "Feriado nacional")
    except Exception as e:
        log.warning(f"consultar_feriado: {e}")
    return ""


async def saludo_matutino(app: Application, chat_id: Optional[int] = None):
    """
    Saludo matutino. Si `chat_id` se da, saluda a ese hogar. Si es None,
    itera todos los hogares registrados. Si no hay ninguno, usa el
    comportamiento legacy (CONFIG global + owner registrado).
    """
    if chat_id is None:
        hogares = hogar_mod.listar_hogares()
        if hogares:
            for cid in hogares:
                await saludo_matutino(app, chat_id=cid)
            return
        # Modo legacy: sin hogares, saluda al owner registrado (si lo hay).

    nombre    = _nombre_adulto_de(chat_id)
    asistente = _nombre_asistente_de(chat_id)
    ciudad    = _ciudad_de(chat_id)

    clima_frase = ""
    try:
        resultado = await consultar_clima(ciudad)
        m = re.search(r"Temperatura (\d+)°C \(sensación (\d+)°C\)", resultado)
        if m:
            temp, sensacion = m.group(1), m.group(2)
            if temp == sensacion:
                clima_frase = f" Hoy en {ciudad.split(',')[0]} hay {temp} grados."
            else:
                clima_frase = f" Hoy en {ciudad.split(',')[0]} hay {temp} grados, con sensación de {sensacion}."
    except Exception as e:
        log.warning(f"saludo_matutino: no pude obtener clima: {e}")

    feriado_frase = ""
    feriado = await consultar_feriado()
    if feriado:
        feriado_frase = (
            f" Hoy es feriado — {feriado}."
            f" Algunos negocios como los bancos pueden no estar abiertos con el horario normal."
        )

    fecha_frase = fecha_en_espanol()
    texto = (
        f"Hola {nombre}, soy {asistente}. Hoy es {fecha_frase}."
        f"{clima_frase}{feriado_frase} ¿Cómo amaneciste hoy?"
    )
    await enviar_mensaje_voz(app, texto, chat_id=chat_id)

async def verificar_inactividad(app: Application, chat_id: Optional[int] = None):
    """
    Verifica inactividad y dispara alerta al familiar si corresponde.

    Multi-tenant: si `chat_id` es None, itera todos los hogares. Para cada
    hogar usa su propia última actividad y su propio "ya alerté hoy".
    Si no hay hogares registrados, usa los globales legacy (compat con tests).
    """
    if chat_id is None:
        hogares = hogar_mod.listar_hogares()
        if hogares:
            for cid in hogares:
                await verificar_inactividad(app, chat_id=cid)
            return
        # Modo legacy: cae al flujo viejo abajo con chat_id=None.

    global _alerta_inactividad_fecha

    cfg = CONFIG.get("alerta_inactividad", {})
    if not cfg.get("activa", True):
        return

    # Baseline de actividad: por hogar si tenemos chat_id, sino el global legacy.
    if chat_id is not None:
        ultima = _ultimas_actividades.get(chat_id)
    else:
        ultima = _ultima_actividad

    if ultima is None:
        log.info(f"Inactividad: sin baseline aún (chat_id={chat_id})")
        return

    horas = (datetime.now() - ultima).total_seconds() / 3600
    umbral = cfg.get("horas_umbral", 4)

    if horas < umbral:
        log.info(f"Inactividad chat_id={chat_id}: {horas:.1f}h — normal ({umbral}h)")
        return

    hoy = datetime.now().date()
    if chat_id is not None:
        if _alertas_inactividad_fecha.get(chat_id) == hoy:
            log.info(f"Inactividad chat_id={chat_id}: ya se alertó hoy")
            return
        _alertas_inactividad_fecha[chat_id] = hoy
    else:
        if _alerta_inactividad_fecha == hoy:
            log.info("Inactividad: ya se alertó hoy")
            return
        _alerta_inactividad_fecha = hoy

    family_bot = app.bot_data.get("family_bot")
    if not family_bot:
        log.warning("Inactividad detectada pero family_bot no está configurado")
        return

    log.info(
        f"Alerta inactividad: {horas:.1f}h sin actividad de "
        f"{_nombre_adulto_de(chat_id)} (chat_id={chat_id})"
    )
    create_background_task(notify_inactividad(
        horas=int(horas),
        ultima_actividad=ultima,
        family_bot=family_bot,
        adulto_chat_id=chat_id,
    ))


def programar_recordatorios(scheduler: AsyncIOScheduler, app: Application):
    """Programa jobs proactivos. Todos iteran sobre los hogares en runtime
    (no en build-time) para soportar hogares que se den de alta después de
    arrancar el bot."""
    saludo_cfg = CONFIG.get("saludo_diario", {})
    if saludo_cfg.get("activo", True):
        hora, minuto = map(int, saludo_cfg.get("hora", "08:30").split(":"))
        scheduler.add_job(
            saludo_matutino, "cron",
            hour=hora, minute=minuto,
            args=[app],
        )

    for r in CONFIG.get("recordatorios", []):
        hora, minuto = map(int, r["hora"].split(":"))
        scheduler.add_job(
            enviar_mensaje_voz, "cron",
            hour=hora, minute=minuto,
            args=[app, r["mensaje"]],
        )
        log.info(f"Recordatorio programado {r['hora']} (todos los hogares): {r['mensaje']}")

    hora_an, minuto_an = map(int, CONFIG.get("analisis_nocturno_hora", "23:30").split(":"))
    scheduler.add_job(analisis_nocturno, "cron", hour=hora_an, minute=minuto_an, args=[app])
    log.info(f"Análisis nocturno programado a las {hora_an:02d}:{minuto_an:02d} (todos los hogares)")

    # Contexto del día: de madrugada lee Google News y arma la lista curada de
    # temas (generales + locales) + dólar + clima. Default 05:20.
    hora_cx, minuto_cx = map(int, CONFIG.get("contexto_dia_hora", "05:20").split(":"))
    scheduler.add_job(actualizar_contexto_del_dia, "cron", hour=hora_cx, minute=minuto_cx, args=[app])
    log.info(f"Contexto del día programado a las {hora_cx:02d}:{minuto_cx:02d} (Google News + dólar + clima)")

    cfg_inact = CONFIG.get("alerta_inactividad", {})
    if cfg_inact.get("activa", True):
        for hora_str in cfg_inact.get("checks", ["11:30", "19:00"]):
            hora, minuto = map(int, hora_str.split(":"))
            scheduler.add_job(
                verificar_inactividad, "cron",
                hour=hora, minute=minuto,
                args=[app],
            )
            log.info(f"Check de inactividad programado a las {hora_str}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Lista que Telegram muestra en el boton de menu azul al lado de la caja de texto.
# Solo exponemos comandos utiles fuera de un flujo de conversacion: /saltar y
# /cancelar viven adentro del onboarding y no tiene sentido ofrecerlos siempre.
COMANDOS_TELEGRAM = [
    BotCommand("start",   "Iniciar o reiniciar la conversacion con Aikiu"),
    BotCommand("invitar", "Generar codigo para vincular un familiar"),
]


async def main():
    log.info("=" * 50)
    log.info("Aikiu iniciando (multi-tenant)")
    log.info("=" * 50)

    # Validación del proveedor LLM: si el chat va por OpenRouter, la key
    # tiene que estar. Se chequea acá (arranque) y no al importar, para
    # que los tests y el CI no necesiten la variable.
    if CONFIG.get("proveedor_llm", "groq") == "openrouter" and not os.environ.get("OPENROUTER_API_KEY", "").strip():
        raise RuntimeError(
            "proveedor_llm es 'openrouter' pero falta OPENROUTER_API_KEY en .env "
            "(o cambiá proveedor_llm a 'groq' en config.yml)"
        )
    log.info(f"LLM de chat: {CONFIG.get('proveedor_llm', 'groq')} / {CONFIG.get('modelo_llm')}")

    # Migración automática del layout legacy single-tenant al multi-tenant.
    # Idempotente: si ya hay hogares en instances/, no hace nada.
    try:
        owner_migrado = migrate_legacy.migrar_si_corresponde()
        if owner_migrado is not None:
            log.info(f"Migración legacy completada para chat_id={owner_migrado}")
    except Exception as e:
        log.warning(f"Migración legacy falló: {e}")

    hogares = hogar_mod.listar_hogares()
    log.info(f"Hogares detectados: {len(hogares)} → {hogares}")

    scheduler = AsyncIOScheduler()

    app = (
        Application.builder()
        .token(CONFIG["bot_token"])
        .build()
    )
    onboarding_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            OB_NOMBRE: [MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), ob_nombre)],
            OB_EDAD:   [MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), ob_edad)],
            OB_CIUDAD: [MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), ob_ciudad)],
            OB_FAMILIA:[MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), ob_familia)],
            OB_GUSTOS: [MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), ob_gustos)],
        },
        fallbacks=[
            CommandHandler("saltar", cmd_saltar),
            CommandHandler("cancelar", cmd_cancelar_onboarding),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
        name="onboarding",
    )
    app.add_handler(onboarding_conv)
    app.add_handler(CommandHandler("invitar", cmd_invitar))
    app.add_handler(MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), handle_message))
    app.add_error_handler(on_error)

    async with app:
        # post_init equivalente — en el patrón async-with, PTB no llama post_init automáticamente
        programar_recordatorios(scheduler, app)
        scheduler.start()
        hb_mod.iniciar_heartbeat("aikiu")

        # Publica los comandos en Telegram para que aparezcan en el botón de menú
        # azul (al lado del campo de texto) apenas el adulto abre el chat.
        try:
            await app.bot.set_my_commands(COMANDOS_TELEGRAM)
            log.info(f"Comandos publicados en Telegram: {len(COMANDOS_TELEGRAM)}")
        except Exception as e:
            log.warning(f"No pude publicar los comandos en Telegram: {e}")

        familiar_token = os.environ.get("FAMILIAR_BOT_TOKEN", "").strip()
        log.info(f"FAMILIAR_BOT_TOKEN: {'presente (' + str(len(familiar_token)) + ' chars)' if familiar_token else 'no encontrado'}")
        if familiar_token and "PEGA_TU" not in familiar_token:
            app.bot_data["family_bot"] = Bot(token=familiar_token)
            log.info("Alertas al familiar activadas — family_bot listo en bot_data")
        else:
            log.warning("Bot familiar no configurado — alertas desactivadas (revisá FAMILIAR_BOT_TOKEN en .env)")

        if not hogares:
            log.warning(
                "Todavía no hay hogares registrados. Cualquiera que mande /start "
                "al bot va a crear el suyo automáticamente."
            )
        else:
            log.info(f"{len(hogares)} hogar(es) activo(s): {hogares}")

        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        log.info("Aikiu escuchando. Ctrl+C para detener.")
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
