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
from datetime import datetime
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

def cargar_config():
    with open(BASE_DIR / "config.yml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key, env_var in [("bot_token", "BOT_TOKEN"), ("chat_id", "CHAT_ID"), ("groq_api_key", "GROQ_API_KEY")]:
        value = os.environ.get(env_var)
        if not value:
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

_DIAS_ES  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def _fecha_hora_es() -> str:
    now = datetime.now()
    return (f"{_DIAS_ES[now.weekday()]} {now.day} de "
            f"{_MESES_ES[now.month - 1]} de {now.year}, {now.strftime('%H:%M')}")


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
        f"\n\nFecha y hora actual: {_fecha_hora_es()} (hora de Buenos Aires)."
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
        "Nunca omitas esta línea. Si no hay señales en el mensaje actual, escribí DISTRESS_LEVEL: 0."
    )
    return prompt


def _norm(s: str) -> str:
    """Minúsculas sin tildes para comparación de keywords."""
    return re.sub(r"[áàä]", "a", re.sub(r"[éèë]", "e", re.sub(r"[íìï]", "i",
           re.sub(r"[óòö]", "o", re.sub(r"[úùü]", "u", s.lower())))))

async def _pre_route(texto: str) -> str:
    """Detecta si el mensaje requiere datos externos y los obtiene antes del LLM."""
    t = _norm(texto)
    if any(w in t for w in ["clima", "tiempo", "temperatura", "grados", "llueve",
                             "lluvia", "frio", "calor", "pronostico", "nublado",
                             "viento", "humedad"]):
        ciudad = CONFIG.get("ciudad", "Buenos Aires")
        # Detectar ciudad mencionada explícitamente: "en Córdoba", "en Mendoza"
        m = re.search(r"\ben\s+([A-ZÁÉÍÓÚ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚ][a-záéíóúñ]+)?)", texto)
        if m:
            ciudad = m.group(1)
        resultado = await consultar_clima(ciudad)
        log.info(f"Pre-route clima({ciudad}) → {resultado[:80]}")
        return resultado

    if any(w in t for w in ["dolar", "cotizacion", "tipo de cambio", "cambio", "billete"]):
        resultado = await consultar_dolar()
        log.info(f"Pre-route dolar → {resultado[:80]}")
        return resultado

    if any(w in t for w in ["noticias", "que paso", "novedades", "titulares", "hoy que"]):
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
    messages.extend(historial[-10:])

    # Pre-routing: obtener datos externos antes del LLM
    datos_externos = await _pre_route(texto_usuario)
    if datos_externos:
        messages.append({
            "role": "system",
            "content": f"Datos en tiempo real para responder este mensaje: {datos_externos}",
        })

    messages.append({"role": "user", "content": texto_usuario})

    response = await groq.chat.completions.create(
        model=modelo,
        messages=messages,
        max_tokens=300,
        temperature=0.7,
    )

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
LOGS_DIR    = BASE_DIR / "logs"

def registrar_log(usuario: str, respuesta: str):
    from datetime import datetime
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

def _actualizar_seccion_perfil(seccion: str, nuevas_lineas: list[str]):
    """Reemplaza el contenido de una sección ## en perfil.md."""
    from datetime import date
    hoy = date.today().strftime("%d/%m/%Y")
    content = PERFIL_PATH.read_text(encoding="utf-8")
    bloque = f"## {seccion}\n" + "".join(f"{l} ({hoy})\n" for l in nuevas_lineas) + "\n"
    import re as _re
    patron = rf"## {seccion}\n.*?(?=\n## |\Z)"
    if _re.search(patron, content, _re.DOTALL):
        # Preservar entradas anteriores: agregar al inicio de la sección existente
        content = content.replace(
            f"## {seccion}\n",
            f"## {seccion}\n" + "".join(f"{l} ({hoy})\n" for l in nuevas_lineas),
        )
    else:
        content = content.rstrip() + f"\n\n## {seccion}\n" + "".join(f"{l} ({hoy})\n" for l in nuevas_lineas) + "\n"
    PERFIL_PATH.write_text(content, encoding="utf-8")

async def analisis_nocturno(app=None):
    """Job nocturno: extrae aprendizajes del log del día y detecta patrones de mejora."""
    from datetime import date
    nombre = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]
    hoy = date.today().strftime("%Y-%m-%d")
    log_path = LOGS_DIR / f"{hoy}.md"
    if not log_path.exists():
        log.info("analisis_nocturno: sin log del día, nada que analizar")
        return

    log_dia = log_path.read_text(encoding="utf-8")
    perfil_actual = PERFIL_PATH.read_text(encoding="utf-8")

    # Extraer sólo la sección Aprendizajes actual para pasarla al LLM
    import re as _re
    m = _re.search(r"## Aprendizajes\n(.*?)(?=\n## |\Z)", perfil_actual, _re.DOTALL)
    aprendizajes_actuales = m.group(1).strip() if m else "(ninguno)"

    prompt = f"""Sos un asistente que analiza conversaciones de {asistente} con {nombre}, una adulta mayor.

--- LOG DEL DÍA ---
{log_dia}

--- APRENDIZAJES YA CONOCIDOS SOBRE {nombre.upper()} ---
{aprendizajes_actuales}

Respondé con exactamente dos secciones:

APRENDIZAJES_NUEVOS:
(listá solo datos concretos y nuevos sobre {nombre} que NO estén ya en los aprendizajes conocidos: eventos, salud, familia, gustos, estado de ánimo. Máximo 5 líneas, cada una empezando con "- ". Si no hay nada nuevo, escribí "ninguno")

AJUSTES_CONVERSACION:
(detectá patrones problemáticos en la conversación de hoy: respuestas cortadas, preguntas innecesarias, temas que {nombre} evitó, etc. Sugerí ajustes concretos para mejorar. Máximo 3 líneas, cada una empezando con "- ". Si la conversación estuvo bien, escribí "ninguno")"""

    try:
        r = await groq.chat.completions.create(
            model=CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.2,
        )
        respuesta = r.choices[0].message.content.strip()
        log.info(f"analisis_nocturno respuesta LLM:\n{respuesta}")

        aprendizajes = _parsear_seccion(respuesta, "APRENDIZAJES_NUEVOS")
        ajustes = _parsear_seccion(respuesta, "AJUSTES_CONVERSACION")

        if aprendizajes:
            _actualizar_seccion_perfil("Aprendizajes", aprendizajes)
            log.info(f"analisis_nocturno: {len(aprendizajes)} aprendizaje(s) nuevo(s)")
        if ajustes:
            _actualizar_seccion_perfil("Ajustes sugeridos", ajustes)
            log.info(f"analisis_nocturno: {len(ajustes)} ajuste(s) sugerido(s)")
    except Exception as e:
        log.warning(f"analisis_nocturno falló: {e}")

def _parsear_seccion(texto: str, seccion: str) -> list[str]:
    """Extrae líneas con '- ' de una sección del output del LLM."""
    import re as _re
    m = _re.search(rf"{seccion}:\n(.*?)(?=\n[A-Z_]+:|\Z)", texto, _re.DOTALL)
    if not m:
        return []
    bloque = m.group(1).strip()
    if bloque.lower() == "ninguno":
        return []
    return [l.strip() for l in bloque.splitlines() if l.strip().startswith("-")]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat_id_autorizado(chat_id: int) -> bool:
    return str(chat_id) == str(CONFIG["chat_id"])

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
    if not chat_id_autorizado(chat_id):
        return
    nombre = CONFIG["nombre_adulto_mayor"]
    asistente = CONFIG["nombre_asistente"]
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

    if should_send_alert(distress_level):
        record_alert_sent(distress_level)
        family_bot     = context.bot_data.get("family_bot")
        family_chat_id = context.bot_data.get("family_chat_id")
        if family_bot:
            log.info(f"Enviando alerta nivel {distress_level} a suscriptores")
            create_background_task(notify_family(
                distress_level=distress_level,
                adulto_message=texto,
                bot_response=respuesta,
                family_bot=family_bot,
                family_chat_id=family_chat_id,
            ))
        else:
            log.warning("Alerta detectada pero family_bot no está configurado — revisar FAMILIAR_BOT_TOKEN en .env")

# ---------------------------------------------------------------------------
# Mensajes proactivos
# ---------------------------------------------------------------------------

async def enviar_mensaje_voz(app: Application, texto: str):
    chat_id = CONFIG["chat_id"]
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "proactivo.ogg"
        await sintetizar(texto, ogg, voz=CONFIG.get("voz_tts", "es-AR-ElenaNeural"))
        with open(ogg, "rb") as audio:
            await app.bot.send_voice(chat_id=chat_id, voice=audio)
    log.info(f"Proactivo enviado: '{texto}'")

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

    texto = f"Buenos días {nombre}, soy {asistente}.{clima_frase} ¿Cómo amaneciste hoy?"
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

    from datetime import date as date_type
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

        familiar_token   = os.environ.get("FAMILIAR_BOT_TOKEN", "")
        familiar_chat_id = os.environ.get("FAMILIAR_CHAT_ID", "")
        log.info(f"FAMILIAR_BOT_TOKEN: {'presente (' + str(len(familiar_token)) + ' chars)' if familiar_token else 'no encontrado'}")
        if familiar_token and "PEGA_TU" not in familiar_token:
            app.bot_data["family_bot"]     = Bot(token=familiar_token)
            app.bot_data["family_chat_id"] = familiar_chat_id
            log.info("Alertas al familiar activadas — family_bot listo en bot_data")
        else:
            log.warning("Bot familiar no configurado — alertas desactivadas (revisá FAMILIAR_BOT_TOKEN en .env)")

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
