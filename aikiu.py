"""
Aikiu — Asistente de voz para adultos mayores via Telegram
STT + LLM: Groq (free tier)
TTS: Telegram voice notes nativos
Sin Ollama, sin Whisper local, sin servidor propio.
"""

import asyncio
import logging
import tempfile
import os
import yaml
import httpx
import edge_tts
from pathlib import Path
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot, Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from groq import AsyncGroq
from core.distress import parse_llm_response, should_send_alert, record_alert_sent
from core.alerts import notify_family

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

async def generar_respuesta(texto_usuario: str, historial: list) -> str:
    asistente = CONFIG["nombre_asistente"]
    perfil    = CONFIG.get("_perfil", "")

    if perfil:
        nombre = CONFIG["nombre_anciano"]
        system_prompt = (
            f"Tu nombre es {asistente}. Sos un asistente de voz.\n"
            f"Hablás con {nombre}. A continuación está su perfil "
            f"y las instrucciones de cómo debés comportarte:\n\n"
            f"{perfil}"
        )
    else:
        nombre = CONFIG["nombre_anciano"]
        system_prompt = (
            f"Sos {asistente}, un asistente de voz para {nombre}. "
            f"Respondé en español rioplatense, oraciones cortas y simples. "
            f"Nunca uses markdown. Máximo 3 oraciones."
        )

    system_prompt += (
        "\n\n---\n"
        "INSTRUCCIÓN DE SISTEMA (no leer en voz alta, no mencionar a Rosa):\n"
        "Al final de CADA respuesta agregá exactamente esta línea:\n"
        "DISTRESS_LEVEL: [0-3]\n"
        "Criterios:\n"
        "- 0: conversación normal\n"
        "- 1: menciona soledad, tristeza, no dormir bien, extrañar a alguien\n"
        "- 2: llora, dice que está muy mal, dolor físico persistente, confusión notoria\n"
        "- 3: menciona hacerse daño, emergencia médica, no puede respirar, caída\n"
        "Nunca omitas esta línea. Si no hay señales, escribí DISTRESS_LEVEL: 0."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial[-10:])
    messages.append({"role": "user", "content": texto_usuario})

    response = await groq.chat.completions.create(
        model=CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
        messages=messages,
        max_tokens=250,
        temperature=0.7,
    )

    respuesta = response.choices[0].message.content.strip()
    log.info(f"LLM raw: '{respuesta}'")
    return respuesta

# ---------------------------------------------------------------------------
# TTS: Microsoft Edge TTS (gratis, sin API key)
# ---------------------------------------------------------------------------

async def sintetizar(texto: str, salida: Path):
    mp3 = salida.with_suffix(".mp3")
    communicate = edge_tts.Communicate(texto, voice=CONFIG.get("voz_tts", "es-AR-ElenaNeural"))
    await communicate.save(str(mp3))
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(mp3), "-c:a", "libopus", str(salida),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    log.info(f"TTS generado: {salida}")

# ---------------------------------------------------------------------------
# Estado de conversación
# ---------------------------------------------------------------------------

historiales: dict[int, list] = {}

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
    entrada = f"**{now.strftime('%H:%M')}**\n- Rosa: {usuario}\n- Clara: {respuesta}\n\n"
    if not log_file.exists():
        log_file.write_text(encabezado + entrada, encoding="utf-8")
    else:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entrada)

def agregar_aprendizaje(linea: str):
    from datetime import date
    hoy = date.today().strftime("%d/%m/%Y")
    entrada = f"{linea} ({hoy})\n"
    content = PERFIL_PATH.read_text(encoding="utf-8")
    if "## Aprendizajes" in content:
        content = content.replace("## Aprendizajes\n", f"## Aprendizajes\n{entrada}")
    else:
        content += f"\n## Aprendizajes\n{entrada}"
    PERFIL_PATH.write_text(content, encoding="utf-8")
    log.info(f"Aprendizaje anotado: {linea.strip()}")

async def extraer_aprendizaje(usuario: str, respuesta: str):
    prompt = (
        f"Conversación:\nRosa: {usuario}\nClara: {respuesta}\n\n"
        "¿Hay algún dato nuevo y específico sobre Rosa que valga la pena recordar "
        "(un evento, estado de ánimo, dato familiar, salud, actividad)? "
        "Si sí, respondé SOLO con una línea que empiece con '- '. "
        "Si no hay nada relevante, respondé exactamente: ninguno"
    )
    try:
        r = await groq.chat.completions.create(
            model=CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.2,
        )
        resultado = r.choices[0].message.content.strip()
        if resultado.lower() != "ninguno" and resultado.startswith("-"):
            agregar_aprendizaje(resultado)
    except Exception as e:
        log.warning(f"extraer_aprendizaje falló: {e}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat_id_autorizado(chat_id: int) -> bool:
    return str(chat_id) == str(CONFIG["chat_id"])

async def responder_con_voz(context, chat_id: int, texto: str):
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "respuesta.ogg"
        await sintetizar(texto, ogg)
        with open(ogg, "rb") as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not chat_id_autorizado(chat_id):
        log.warning(f"chat_id no autorizado: {chat_id}")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")

    # Obtener texto — voz o texto plano
    if update.message.voice:
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

    await responder_con_voz(context, chat_id, respuesta)

    # Tareas en background (no bloquean la respuesta a Rosa)
    registrar_log(texto, respuesta)
    asyncio.create_task(extraer_aprendizaje(texto, respuesta))

    if should_send_alert(distress_level):
        record_alert_sent(distress_level)
        family_bot     = context.bot_data.get("family_bot")
        family_chat_id = context.bot_data.get("family_chat_id")
        if family_bot and family_chat_id:
            asyncio.create_task(notify_family(
                distress_level=distress_level,
                rosa_message=texto,
                bot_response=respuesta,
                family_bot=family_bot,
                family_chat_id=family_chat_id,
            ))

# ---------------------------------------------------------------------------
# Mensajes proactivos
# ---------------------------------------------------------------------------

async def enviar_mensaje_voz(app: Application, texto: str):
    chat_id = CONFIG["chat_id"]
    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "proactivo.ogg"
        await sintetizar(texto, ogg)
        with open(ogg, "rb") as audio:
            await app.bot.send_voice(chat_id=chat_id, voice=audio)
    log.info(f"Proactivo enviado: '{texto}'")

def programar_recordatorios(scheduler: AsyncIOScheduler, app: Application):
    nombre    = CONFIG["nombre_anciano"]
    asistente = CONFIG["nombre_asistente"]

    saludo_cfg = CONFIG.get("saludo_diario", {})
    if saludo_cfg.get("activo", True):
        hora, minuto = map(int, saludo_cfg.get("hora", "08:30").split(":"))
        scheduler.add_job(
            enviar_mensaje_voz, "cron",
            hour=hora, minute=minuto,
            args=[app, f"Buenos días {nombre}, soy {asistente}. ¿Cómo amaneciste hoy?"],
        )

    for r in CONFIG.get("recordatorios", []):
        hora, minuto = map(int, r["hora"].split(":"))
        scheduler.add_job(
            enviar_mensaje_voz, "cron",
            hour=hora, minute=minuto,
            args=[app, r["mensaje"]],
        )
        log.info(f"Recordatorio programado {r['hora']}: {r['mensaje']}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    log.info("=" * 50)
    log.info(f"Aikiu iniciando para {CONFIG['nombre_anciano']}")
    log.info("=" * 50)

    scheduler = AsyncIOScheduler()

    async def post_init(application: Application) -> None:
        programar_recordatorios(scheduler, application)
        scheduler.start()

        familiar_token   = os.environ.get("FAMILIAR_BOT_TOKEN", "")
        familiar_chat_id = os.environ.get("FAMILIAR_CHAT_ID", "")
        if familiar_token and "PEGA_TU" not in familiar_token:
            application.bot_data["family_bot"]     = Bot(token=familiar_token)
            application.bot_data["family_chat_id"] = familiar_chat_id
            log.info("Alertas al familiar activadas")
        else:
            log.info("Bot familiar no configurado — alertas desactivadas")

        log.info("Aikiu escuchando. Ctrl+C para detener.")

    app = (
        Application.builder()
        .token(CONFIG["bot_token"])
        .post_init(post_init)
        .build()
    )
    app.add_handler(MessageHandler(filters.VOICE | (filters.TEXT & ~filters.COMMAND), handle_message))

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        try:
            await asyncio.Event().wait()
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
