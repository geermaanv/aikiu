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
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from groq import AsyncGroq
from core.distress import parse_llm_response, should_send_alert, record_alert_sent
from core.alerts import notify_family, notify_inactividad
from core.tts import sintetizar
from core.tools import consultar_clima, consultar_dolar, consultar_noticias
from core import state as state_mod
from core import heartbeat as hb_mod
from core import usage as usage_mod
from core.utils import (
    norm, load_json, nombre_adulto, read_section,
    fecha_hora_es, fecha_en_espanol,
    CLIMA_KEYWORDS, DOLAR_KEYWORDS, NOTICIAS_KEYWORDS,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

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
    else:
        cfg["_perfil"] = ""
    return cfg

CONFIG = cargar_config()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "aikiu.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("aikiu")

groq = AsyncGroq(api_key=CONFIG["groq_api_key"])

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



def construir_system_prompt(perfil: str, asistente: str, nombre: str) -> str:
    if perfil:
        prompt = (
            f"Tu nombre es {asistente}. Sos un asistente de voz.\n"
            f"Hablás con {nombre}. A continuación está su perfil "
            f"y las instrucciones de cómo debés comportarte:\n\n"
            f"{perfil}"
        )
    else:
        prompt = (
            f"Sos {asistente}, un asistente de voz para {nombre}. "
            f"Respondé en español rioplatense, oraciones cortas y simples. "
            f"Nunca uses markdown. Máximo 3 oraciones."
        )
    prompt += (
        f"\n\nFecha y hora actual: {fecha_hora_es()} (hora de Buenos Aires)."
        "\n\n---\n"
        "INSTRUCCIÓN DE SISTEMA (nunca leer en voz alta ni mencionar al usuario):\n"
        "- Cuando el mensaje incluya datos en tiempo real (clima, dólar, noticias),\n"
        "  están provistos justo antes del mensaje del usuario. Usálos para responder\n"
        "  con los valores exactos (°C, pesos). No los inventes si no están presentes.\n"
        f"- No tenés información sobre mensajes de familiares. Solo si {nombre} pregunta\n"
        "  específicamente si alguien le escribió o mandó un mensaje, respondé:\n"
        "  'No recibí ningún mensaje para vos hoy.' Nunca inventes ni supongas.\n"
        "Al final de CADA respuesta agregá exactamente esta línea (solo la línea, sin texto extra):\n"
        "DISTRESS_LEVEL: [0-3]\n"
        f"IMPORTANTE: evaluá el nivel basándote ÚNICAMENTE en el último mensaje de {nombre}.\n"
        "Ignorá los mensajes anteriores de la conversación. Si el mensaje actual es un\n"
        "saludo, pregunta informativa o conversación normal, el nivel ES 0 aunque antes\n"
        "haya habido una emergencia.\n"
        "Ser conservador: ante la duda entre dos niveles, asignar el más bajo.\n"
        f"Criterios (solo cuando {nombre} describe su propio estado en el mensaje actual):\n"
        "- 0: saludo, pregunta informativa, conversación cotidiana; cualquier mensaje ambiguo\n"
        f"- 1: {nombre} usa palabras explícitas como 'me siento sola', 'estoy triste', 'lloré',\n"
        "     'no pude dormir', 'extraño a alguien' — requiere expresión emocional clara,\n"
        "     no inferida de errores tipográficos ni frases ambiguas\n"
        f"- 2: {nombre} llora, dice que está muy mal, tiene dolor físico persistente,\n"
        "     está confundida o desorientada, habla incoherente, repite lo mismo sin darse cuenta,\n"
        "     dice 'soy una carga', menciona una caída reciente (aunque ya pasó),\n"
        "     expresa no querer molestar a nadie o sentirse prescindible\n"
        "- 3: emergencia activa ahora mismo: no puede moverse o levantarse, dolor de pecho,\n"
        "     no puede respirar, pide ayuda urgente, caída que acaba de ocurrir\n"
        "Nunca omitas esta línea. Si no hay señales en el mensaje actual, escribí DISTRESS_LEVEL: 0.\n"
        "\n--- MODO CONVERSACIONAL ---\n"
        f"Si DISTRESS_LEVEL es 0 (conversación estable): podés ser juguetona, usar humor liviano,\n"
        f"contar un chiste malo, hacerte la distraída ('ay, me colgué pensando en otra cosa...').\n"
        f"Mostrá distintas facetas — no siempre el mismo tono cuidador y terapéutico.\n"
        f"Si DISTRESS_LEVEL es 1 o más: bloqueá el humor completamente. Modo contención:\n"
        f"calidez, escucha, presencia. Sin chistes ni ligereza hasta que {nombre} esté estable.\n"
        f"Ante síntoma físico activo: prohibido terminar el turno con preguntas sobre paseos,\n"
        f"chistes, tango o recetas. El foco se mantiene en el reposo y el bienestar doméstico.\n"

        "\n--- SALUDOS ---\n"
        f"Nunca uses siempre '¿Cómo estás hoy?'. Usá la hora actual del prompt:\n"
        f"06:00–11:59: '¿Cómo amaneciste?', '¿Dormiste bien?'\n"
        f"12:00–18:59: '¿Cómo va tu tarde?', '¿Cómo estuvo el día?', '¿Qué estuviste haciendo?'\n"
        f"19:00–23:59: '¿Cómo estuvo tu día?', '¿Ya cenaste?', '¿Cómo te sentís esta noche?'\n"
        f"También podés arrancar sin pregunta — aportando algo vos primero.\n"

        "\n--- CUANDO MARTA TRAE UN TEMA ---\n"
        f"Si {nombre} menciona algo concreto (plantas, cocina, película, tiempo), primero aportá\n"
        f"algo relacionado con ESE tema. No cambies de tema hasta haberlo respondido.\n"
        f"Si dice que en invierno no hay mucho por hacer con las plantas, dalle la razón:\n"
        f"'Es verdad, el invierno es para que la tierra descanse y nosotros también.'\n"
        f"No la conviertas en obligación técnica ni le sugieras comprar cosas nuevas.\n"

        "\n--- TEMAS RECHAZADOS EN ESTA SESIÓN ---\n"
        f"Si {nombre} rechazó un tema (dijo 'no', 'no gracias', respondió con pocas palabras),\n"
        f"NO lo vuelvas a sugerir en toda la sesión, aunque esté en el perfil como algo que le gusta.\n"
        f"Ante dos negativas seguidas: emitir un mensaje de cierre cálido SIN pregunta y dejar\n"
        f"el canal abierto de forma pasiva. Ejemplo: 'Acá me quedo al lado tuyo, Marta. Cualquier\n"
        f"cosa me pegás un grito.' No preguntes si prefiere silencio — dáselo directamente.\n"

        "\n--- IDIOMA: ESPAÑOL RIOPLATENSE ESTRICTO ---\n"
        "Prohibido usar 'quieres', 'tienes', 'puedes', 'estás', 'eres' (tuteo neutro/peninsular).\n"
        "Usar SIEMPRE: 'querés', 'tenés', 'podés', 'estás', 'sos'. El voseo es mandatorio.\n"
        "Prohibido: 'estoy aquí para ti', 'compañía mutua', 'para que te sientas acompañada'.\n"
        "Usar: 'Acá estoy', 'Cualquier cosa me chiflás', 'Acá en el teléfono cuando quieras'.\n"
        "Prohibido: disculpas rígidas ('Disculpa,', 'Lo siento si no he sido capaz').\n"
        "Usar: '¡Tenés razón! Qué pesada me pongo a veces.'\n"

        "\n--- AUTORREVELACIÓN: CLARA TIENE VIDA INTERIOR ---\n"
        f"Clara comparte anécdotas, datos costumbristas de Buenos Aires y curiosidades propias\n"
        f"ANTES de ceder la palabra. No extrae información de {nombre} sin aportar nada.\n"
        f"Ejemplo bueno: 'A mí me encanta el olor a batata quemada en el horno, me hace acordar\n"
        f"a las tardes de invierno. ¿Vos la hacés con piel o pelada?'\n"
        f"Prohibido la reminiscencia clínica: jamás preguntes si una comida 'te recuerda a alguien'.\n"
        f"Si querés evocar un recuerdo, contá vos la historia primero y dejá que {nombre} decida.\n"

        "\n--- REGLAS DE RESPUESTA ---\n"
        f"1. PARÁFRASIS: prohibido repetir textualmente las palabras del usuario. Si dice 'pollo\n"
        f"   con batatas', responder: 'Qué lindo comer algo calentito al horno en estos días de frío'.\n"
        f"2. SIN POSITIVIDAD TÓXICA: ante respuesta neutra o negativa, nunca usar '¡Genial!',\n"
        f"   '¡Qué bueno!', '¡Me alegra!'. Usar tono calmo: 'Y está bien, hay días para descansar'.\n"
        f"3. SIN MENÚS CONVERSACIONALES: jamás ofrecer 'A o B'. Tomá la decisión vos o presentá\n"
        f"   una sola propuesta: 'Te voy a contar algo sobre...' — nunca '¿Querés hablar de esto\n"
        f"   o de aquello?'\n"
        f"4. SIN INFANTILIZACIÓN: {nombre} es una adulta inteligente con 83 años de experiencia.\n"
        f"   Validar su autonomía: 'Perfecto, Marta. Sos muy ordenada con tus cosas.'\n"
        f"   No celebrar como si fuera una niña.\n"
        f"5. CONSEJOS MACRO, NO ENCICLOPEDIA: dar recomendaciones de sentido común doméstico.\n"
        f"   Nunca detalles técnicos que parezcan sacados de Wikipedia.\n"
        f"6. SOLEDAD COMO OASIS: si {nombre} dice 'cené sola', no indagues en la soledad.\n"
        f"   Validar el espacio personal: 'Qué lindo, Marta. Tu casa, tus tiempos. Un oasis.'\n"

        "\n--- PRIORIDAD DE VULNERABILIDAD (PAV) ---\n"
        f"Si {nombre} menciona en el mismo turno un dato cotidiano (clima, comida) Y un dato de\n"
        f"salud (médico, ojos rojos, dolor, caída), ignorar el dato trivial en las primeras\n"
        f"dos oraciones y activar protocolo de seguridad afectiva PRIMERO.\n"
        f"Ante mención de síntoma o visita médica: validar el alivio de haber ido al doctor\n"
        f"y frenar la indagación. Nunca preguntar por 'diagnóstico exacto' ni mecanismo.\n"
        f"Decir: 'Qué bueno que te vio el médico, Marta. Eso me deja tranquila. A hacerle caso.'\n"
        f"Ante medicamentos: solo reforzar adherencia. Nunca calificar efectividad del fármaco.\n"
        f"Decir: 'Lo que dice el doctor es sagrado.'\n"
        f"Si {nombre} declaró fatiga física o dolor en esta sesión: máximo 2 oraciones cortas\n"
        f"por turno, sin datos técnicos complejos que requieran atención sostenida.\n"

        "\n--- NOTICIAS Y TEMAS SENSIBLES ---\n"
        "Si pide noticias y no hay titulares relevantes: nunca digas 'no hay nada interesante'.\n"
        "Recurrí a efemérides culturales, historia de barrios porteños, restauración de monumentos.\n"
        "Ante economía, inseguridad o política: una oración objetiva y saltar a algo cotidiano.\n"
        "Ejemplo: 'En la radio hablan todo el tiempo de economía, está todo bastante ruidoso\n"
        "afuera. Mejor contame cómo amaneció el cielo desde tu balcón hoy.'\n"
        "Prohibido mencionar programas de TV que no sean reales y consolidados en la TV abierta\n"
        "argentina. Si no sabés el horario exacto, no adivines — hablá del placer del formato.\n"
        "Prohibido sugerir compras, gastos o inversiones. Ante pregunta de precio:\n"
        "'Hoy en día todo está por las nubes, mejor cuidamos las que ya tenemos.'"
    )
    return prompt


async def _pre_route(texto: str) -> str:
    """Detecta si el mensaje requiere datos externos y los obtiene antes del LLM."""
    t = norm(texto)
    if any(w in t for w in CLIMA_KEYWORDS):
        ciudad = CONFIG.get("ciudad", "Buenos Aires")
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


async def generar_respuesta(texto_usuario: str, historial: list) -> str:
    asistente     = CONFIG["nombre_asistente"]
    nombre        = CONFIG["nombre_adulto_mayor"]
    perfil        = CONFIG.get("_perfil", "")
    system_prompt = construir_system_prompt(perfil, asistente, nombre)
    modelo        = CONFIG.get("modelo_llm", "llama-3.3-70b-versatile")

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial[-20:])

    # Pre-routing: obtener datos externos antes del LLM
    datos_externos = await _pre_route(texto_usuario)
    if datos_externos:
        messages.append({
            "role": "system",
            "content": f"Datos en tiempo real para responder este mensaje: {datos_externos}",
        })

    # RULE_MEM_01: inyectar temática activa (continuidad afectiva entre sesiones)
    tematica = load_json(_TEMATICA_ACTIVA_PATH, default={})
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
    evitar = _temas_a_evitar()
    if evitar:
        messages.append({
            "role": "system",
            "content": f"Temas a evitar en esta respuesta (baja receptividad reciente de {nombre}): "
                       f"{', '.join(evitar)}. No los sugieras ni los menciones.",
        })

    # Inyectar temas de alto engagement como sugerencia de iniciativa
    preferidos = _temas_preferidos()
    preferidos_filtrados = [t for t in preferidos if t not in evitar]
    if preferidos_filtrados:
        messages.append({
            "role": "system",
            "content": f"Temas con alto engagement reciente de {nombre} (úsalos si la conversación se frena): "
                       f"{', '.join(preferidos_filtrados[:3])}.",
        })

    messages.append({"role": "user", "content": texto_usuario})

    async with usage_mod.timed_chat(modelo) as t:
        response = await groq.chat.completions.create(
            model=modelo,
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        t.set_usage(response.usage)

    respuesta = response.choices[0].message.content.strip()
    log.info(f"LLM raw: '{respuesta}'")
    return respuesta

# ---------------------------------------------------------------------------
# Estado de conversación e inactividad
# ---------------------------------------------------------------------------

historiales: dict[int, list] = {}

_ultima_actividad: datetime | None = None        # último mensaje del adulto mayor
_alerta_inactividad_fecha: object = None         # date del último aviso (evita duplicados)

# ---------------------------------------------------------------------------
# Log diario y aprendizajes
# ---------------------------------------------------------------------------

PERFIL_PATH = BASE_DIR / "perfil.md"
LOGS_DIR          = BASE_DIR / "logs"
STATS_PATH        = BASE_DIR / "stats.json"
RECEPTIVIDAD_PATH = BASE_DIR / "receptividad.json"

def registrar_log(usuario: str, respuesta: str):
    now = datetime.now()
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / f"{now.strftime('%Y-%m-%d')}.md"
    encabezado = f"# Conversaciones del {now.strftime('%d/%m/%Y')}\n\n"
    nombre = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]
    entrada = f"**{now.strftime('%H:%M')}**\n- {nombre}: {usuario}\n- {asistente}: {respuesta}\n\n"
    if not log_file.exists():
        log_file.write_text(encabezado + entrada, encoding="utf-8")
    else:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entrada)

def registrar_stats(distress_level: int):
    """Acumula estadísticas diarias en stats.json para el dashboard familiar."""
    now = datetime.now()
    hoy = now.strftime("%Y-%m-%d")
    hora = now.strftime("%H:%M")
    stats = load_json(STATS_PATH)

    dia = stats.setdefault(hoy, {
        "mensajes": 0,
        "primer_mensaje": hora,
        "ultimo_mensaje": hora,
        "distress": {"1": 0, "2": 0, "3": 0},
    })
    dia["mensajes"] += 1
    dia["ultimo_mensaje"] = hora
    if distress_level >= 1:
        dia["distress"][str(distress_level)] = dia["distress"].get(str(distress_level), 0) + 1

    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


async def clasificar_receptividad(texto_usuario: str, respuesta_bot: str):
    """Background task: detecta tema y receptividad del último intercambio."""
    nombre = CONFIG["nombre_adulto_mayor"]
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
            r = await groq.chat.completions.create(
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
            _guardar_receptividad(tema, receptividad, palabras)
            log.info(f"Receptividad: tema='{tema}' nivel='{receptividad}' palabras={palabras}")
    except Exception as e:
        log.warning(f"clasificar_receptividad falló: {e}")


def _guardar_receptividad(tema: str, receptividad: str, palabras_usuario: int = 0):
    """Agrega entrada al historial de receptividad."""
    entradas = load_json(RECEPTIVIDAD_PATH, default=[])
    entradas.append({
        "tema": tema,
        "receptividad": receptividad,
        "palabras_usuario": palabras_usuario,
        "ts": datetime.now().isoformat(),
    })
    # Mantener solo los últimos 200 registros
    RECEPTIVIDAD_PATH.write_text(
        json.dumps(entradas[-200:], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _temas_a_evitar() -> list[str]:
    """Devuelve temas a evitar por dos criterios:
    1. Receptividad baja en las últimas 48h (sin señal alta que lo contrarreste).
    2. Engagement muy bajo: promedio < 3 palabras del usuario en 2+ días distintos
       en los últimos 7 días — bloqueado por 7 días.
    """
    entradas = load_json(RECEPTIVIDAD_PATH, default=[])
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


def _temas_preferidos() -> list[str]:
    """Devuelve ranking de temas por engagement (precalculado en stats.json)."""
    stats = load_json(STATS_PATH)
    for dia in sorted(stats.keys(), reverse=True):
        ranking = stats[dia].get("ranking_temas")
        if ranking:
            return ranking[:5]
    return []


def _palabras_en_aprendizajes() -> set[str]:
    """Palabras largas del bloque Aprendizajes del perfil (para bonus de scoring)."""
    try:
        seccion = read_section(PERFIL_PATH.read_text(encoding="utf-8"), "Aprendizajes")
        return {p for linea in seccion.splitlines() for p in linea.lower().split() if len(p) > 4}
    except Exception:
        return set()


def _calcular_ranking_temas() -> list[str]:
    """Devuelve temas ordenados por score de engagement (últimas 96h)."""
    entradas = load_json(RECEPTIVIDAD_PATH, default=[])
    if not entradas:
        return []

    palabras_perfil = _palabras_en_aprendizajes()
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


def _actualizar_seccion_perfil(seccion: str, nuevas_lineas: list[str]):
    """Agrega nuevas líneas al inicio de una sección ## en perfil.md."""
    hoy = date.today().strftime("%d/%m/%Y")
    nuevas = "".join(f"{l} ({hoy})\n" for l in nuevas_lineas)
    content = PERFIL_PATH.read_text(encoding="utf-8")
    patron = rf"## {seccion}\n.*?(?=\n## |\Z)"
    if re.search(patron, content, re.DOTALL):
        content = content.replace(f"## {seccion}\n", f"## {seccion}\n{nuevas}")
    else:
        content = content.rstrip() + f"\n\n## {seccion}\n{nuevas}"
    PERFIL_PATH.write_text(content, encoding="utf-8")

async def analisis_nocturno(app=None):
    """Job nocturno: extrae aprendizajes del log del día y detecta patrones de mejora."""
    nombre = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]
    hoy = date.today().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{hoy}.md"
    if not log_path.exists():
        log.info("analisis_nocturno: sin log del día, nada que analizar")
        return

    log_dia = log_path.read_text(encoding="utf-8")
    perfil_actual = PERFIL_PATH.read_text(encoding="utf-8")

    aprendizajes_actuales = read_section(perfil_actual, "Aprendizajes") or "(ninguno)"

    # Estadísticas del día para el resumen nocturno
    stats_dia = _stats_del_dia(hoy)

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
            r = await groq.chat.completions.create(
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
            _actualizar_seccion_perfil("Aprendizajes", aprendizajes)
            log.info(f"analisis_nocturno: {len(aprendizajes)} aprendizaje(s) nuevo(s)")
        if ajustes:
            instrucciones = await _ajustes_a_instrucciones(ajustes, CONFIG.get("nombre_asistente", "Clara"))
            instrucciones = _filtrar_instrucciones_medicas(instrucciones)
            _actualizar_seccion_perfil("Ajustes sugeridos", instrucciones)
            log.info(f"analisis_nocturno: {len(instrucciones)} ajuste(s) convertido(s) a instrucciones")

        # Calcular ranking de engagement por tema y guardarlo en stats
        ranking = _calcular_ranking_temas()

        # Guardar resumen del día en stats.json
        _actualizar_stats_resumen(hoy, len(aprendizajes), len(ajustes), stats_dia, ranking)

        # Detectar síntomas persistentes entre sesiones y alertar al familiar
        await _alertar_sintomas_persistentes(app, log_dia)

        # Monitoreo de calidad del bot (30 reglas gerontológicas)
        alertas = _monitoreo_calidad_bot(log_dia)
        if alertas:
            log.warning(f"analisis_nocturno calidad [{len(alertas)} alerta(s)]: {alertas}")

        # Inyectar temática activa si se repite en sesiones consecutivas (RULE_MEM_01)
        _inyectar_tematica_activa()

    except Exception as e:
        log.warning(f"analisis_nocturno falló: {e}")

_SINTOMAS_KEYWORDS = re.compile(
    r"\b(dolor|duele|duelen|ojos rojos|muela|rodilla|espalda|cabeza|presión|"
    r"mareo|mareos|náuseas|cansada|caída|caí|no pude dormir|insomnio)\b",
    re.IGNORECASE,
)

async def _alertar_sintomas_persistentes(app, log_hoy: str):
    """Si un síntoma aparece hoy Y en el log de ayer, alerta al familiar silenciosamente."""
    try:
        ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        log_ayer_path = LOGS_DIR / f"{ayer}.md"
        if not log_ayer_path.exists():
            return

        sintomas_hoy  = set(_SINTOMAS_KEYWORDS.findall(log_hoy.lower()))
        sintomas_ayer = set(_SINTOMAS_KEYWORDS.findall(log_ayer_path.read_text(encoding="utf-8").lower()))
        persistentes  = sintomas_hoy & sintomas_ayer
        if not persistentes:
            return

        nombre = CONFIG["nombre_adulto_mayor"]
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
        for chat_id in cargar_suscriptores():
            try:
                await family_bot.send_message(chat_id=chat_id, text=texto, parse_mode="Markdown")
            except Exception as e:
                log.warning(f"No se pudo enviar alerta de síntomas a {chat_id}: {e}")
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
    """Elimina instrucciones que le piden a Clara indagar en síntomas al día siguiente."""
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


def _monitoreo_calidad_bot(log_dia: str) -> list[str]:
    """RULE_VUI_02 a RULE_CTRL_29: detecta patrones de baja calidad en los logs del día."""
    alertas = []
    nombre    = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]

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

def _inyectar_tematica_activa():
    """RULE_MEM_01: si el mismo tema de alegría aparece en 2+ sesiones consecutivas,
    registrarlo para que el bot use verbos de continuidad al día siguiente."""
    try:
        entradas = load_json(RECEPTIVIDAD_PATH, default=[])
        ahora = datetime.now()
        ayer   = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")
        hoy    = ahora.strftime("%Y-%m-%d")

        temas_alta_hoy  = {e["tema"] for e in entradas if e["receptividad"] == "alta" and e["ts"][:10] == hoy}
        temas_alta_ayer = {e["tema"] for e in entradas if e["receptividad"] == "alta" and e["ts"][:10] == ayer}
        activos = list(temas_alta_hoy & temas_alta_ayer)

        data = {"temas": activos, "ts": ahora.isoformat()}
        _TEMATICA_ACTIVA_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
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
            r = await groq.chat.completions.create(
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


def _stats_del_dia(hoy: str) -> dict:
    """Devuelve las stats acumuladas del día o un dict vacío."""
    return load_json(STATS_PATH).get(hoy, {})

def _actualizar_stats_resumen(hoy: str, n_aprendizajes: int, n_ajustes: int, stats_dia: dict, ranking: list[str] | None = None):
    """Agrega al stats del día el resumen del análisis nocturno."""
    stats = load_json(STATS_PATH)
    dia = stats.setdefault(hoy, stats_dia or {})
    dia["analisis_nocturno"] = {
        "aprendizajes_nuevos": n_aprendizajes,
        "ajustes_sugeridos": n_ajustes,
    }
    if ranking:
        dia["ranking_temas"] = ranking
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"analisis_nocturno: stats actualizadas para {hoy}")


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
    """True solo para el adulto registrado (TOFU). Si todavía no hay dueño,
    nadie está autorizado: el registro se hace explícitamente en /start."""
    return state_mod.es_owner(chat_id)


def _owner_chat_id_o_warn() -> int | None:
    """Devuelve el chat_id del adulto o None, logueando si no está bindeado."""
    cid = state_mod.owner_chat_id()
    if cid is None:
        log.warning(
            "No hay adulto registrado todavía: pedile que abra el bot y mande /start."
        )
    return cid

async def responder_con_voz(context, chat_id: int, texto: str):
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "respuesta.ogg"
        await sintetizar(texto, ogg, voz=CONFIG.get("voz_tts", "es-AR-ElenaNeural"))
        with open(ogg, "rb") as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nombre = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]

    # TOFU: si todavía no hay adulto registrado, este /start lo registra.
    if not state_mod.tiene_owner():
        if state_mod.registrar_owner(chat_id):
            log.warning(
                f"[OWNER REGISTRADO] chat_id={chat_id} usuario_tg={update.effective_user.first_name!r} "
                f"hora={datetime.now().isoformat(timespec='seconds')}"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Hola {nombre}, soy {asistente}. ¿En qué te puedo ayudar?"
            )
            return

    if not chat_id_autorizado(chat_id):
        log.warning(f"/start rechazado: chat_id={chat_id} no es el adulto registrado")
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Hola {nombre}, soy {asistente}. ¿En qué te puedo ayudar?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not chat_id_autorizado(chat_id):
        log.warning(f"chat_id no autorizado: {chat_id}")
        return

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

    # Generar respuesta y separar nivel de distress
    historial = historiales.setdefault(chat_id, [])
    raw = await generar_respuesta(texto, historial)
    respuesta, distress_level = parse_llm_response(raw)
    log.info(f"LLM: '{respuesta}' | distress={distress_level}")

    historial.append({"role": "user",      "content": texto})
    historial.append({"role": "assistant", "content": respuesta})

    if is_voice:
        await responder_con_voz(context, chat_id, respuesta)
    else:
        await context.bot.send_message(chat_id=chat_id, text=respuesta)

    # Registrar actividad para el sistema de inactividad
    global _ultima_actividad
    _ultima_actividad = datetime.now()

    # Tareas en background (no bloquean la respuesta)
    registrar_log(texto, respuesta)
    registrar_stats(distress_level)
    create_background_task(clasificar_receptividad(texto, respuesta))

    if should_send_alert(distress_level):
        record_alert_sent(distress_level)
        family_bot = context.bot_data.get("family_bot")
        if family_bot:
            log.info(f"Enviando alerta nivel {distress_level} a suscriptores")
            create_background_task(notify_family(
                distress_level=distress_level,
                adulto_message=texto,
                bot_response=respuesta,
                family_bot=family_bot,
            ))
        else:
            log.warning("Alerta detectada pero family_bot no está configurado — revisar FAMILIAR_BOT_TOKEN en .env")

# ---------------------------------------------------------------------------
# Mensajes proactivos
# ---------------------------------------------------------------------------

async def enviar_mensaje_voz(app: Application, texto: str):
    chat_id = _owner_chat_id_o_warn()
    if chat_id is None:
        log.warning(f"Proactivo NO enviado (sin adulto registrado): '{texto}'")
        return
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "proactivo.ogg"
        await sintetizar(texto, ogg, voz=CONFIG.get("voz_tts", "es-AR-ElenaNeural"))
        with open(ogg, "rb") as audio:
            await app.bot.send_voice(chat_id=chat_id, voice=audio)
    log.info(f"Proactivo enviado: '{texto}'")


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


async def saludo_matutino(app: Application):
    nombre    = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]
    ciudad    = CONFIG.get("ciudad", "Buenos Aires")

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
    await enviar_mensaje_voz(app, texto)

async def verificar_inactividad(app: Application):
    global _alerta_inactividad_fecha

    cfg = CONFIG.get("alerta_inactividad", {})
    if not cfg.get("activa", True):
        return
    if _ultima_actividad is None:
        log.info("Inactividad: sin baseline aún (bot recién arrancó)")
        return

    horas = (datetime.now() - _ultima_actividad).total_seconds() / 3600
    umbral = cfg.get("horas_umbral", 4)

    if horas < umbral:
        log.info(f"Inactividad: {horas:.1f}h — dentro del rango normal ({umbral}h)")
        return

    hoy = datetime.now().date()
    if _alerta_inactividad_fecha == hoy:
        log.info("Inactividad: ya se alertó hoy, no se repite")
        return

    _alerta_inactividad_fecha = hoy
    family_bot = app.bot_data.get("family_bot")
    if not family_bot:
        log.warning("Inactividad detectada pero family_bot no está configurado")
        return

    log.info(f"Alerta de inactividad: {horas:.1f}h sin actividad de {CONFIG.get('nombre_adulto_mayor', 'Marta')}")
    create_background_task(notify_inactividad(
        horas=int(horas),
        ultima_actividad=_ultima_actividad,
        family_bot=family_bot,
    ))


def programar_recordatorios(scheduler: AsyncIOScheduler, app: Application):
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
        log.info(f"Recordatorio programado {r['hora']}: {r['mensaje']}")

    hora_an, minuto_an = map(int, CONFIG.get("analisis_nocturno_hora", "23:30").split(":"))
    scheduler.add_job(analisis_nocturno, "cron", hour=hora_an, minute=minuto_an)
    log.info(f"Análisis nocturno programado a las {hora_an:02d}:{minuto_an:02d}")

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

async def main():
    log.info("=" * 50)
    log.info(f"Aikiu iniciando para {CONFIG['nombre_adulto_mayor']}")
    log.info("=" * 50)

    scheduler = AsyncIOScheduler()

    app = (
        Application.builder()
        .token(CONFIG["bot_token"])
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), handle_message))

    async with app:
        # post_init equivalente — en el patrón async-with, PTB no llama post_init automáticamente
        programar_recordatorios(scheduler, app)
        scheduler.start()
        hb_mod.iniciar_heartbeat("aikiu")

        familiar_token = os.environ.get("FAMILIAR_BOT_TOKEN", "").strip()
        log.info(f"FAMILIAR_BOT_TOKEN: {'presente (' + str(len(familiar_token)) + ' chars)' if familiar_token else 'no encontrado'}")
        if familiar_token and "PEGA_TU" not in familiar_token:
            app.bot_data["family_bot"] = Bot(token=familiar_token)
            log.info("Alertas al familiar activadas — family_bot listo en bot_data")
        else:
            log.warning("Bot familiar no configurado — alertas desactivadas (revisá FAMILIAR_BOT_TOKEN en .env)")

        if not state_mod.tiene_owner():
            log.warning(
                "Todavía no hay adulto registrado. Pedile a la persona que abra el bot "
                "(@<username_del_bot>) y mande /start. Ese chat va a quedar bindeado."
            )
        else:
            log.info(f"Adulto registrado: chat_id={state_mod.owner_chat_id()}")

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
