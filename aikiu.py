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
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from groq import AsyncGroq

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent

def cargar_config():
    with open(BASE_DIR / "config.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)

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
    nombre    = CONFIG["nombre_anciano"]
    asistente = CONFIG["nombre_asistente"]
    personalidad = CONFIG.get("personalidad", "amigable, paciente, habla simple y claro")

    system_prompt = (
        f"Sos {asistente}, un asistente de voz para {nombre}. "
        f"Tu personalidad: {personalidad}. "
        f"Respondé siempre en español rioplatense, con oraciones cortas y simples. "
        f"Nunca uses markdown, listas ni símbolos especiales. "
        f"Solo texto natural pensado para ser escuchado, no leído. "
        f"Máximo 3 oraciones por respuesta."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(historial[-10:])
    messages.append({"role": "user", "content": texto_usuario})

    response = await groq.chat.completions.create(
        model=CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
        messages=messages,
        max_tokens=200,
        temperature=0.7,
    )

    respuesta = response.choices[0].message.content.strip()
    log.info(f"LLM: '{respuesta}'")
    return respuesta

# ---------------------------------------------------------------------------
# TTS: Groq PlayAI
# ---------------------------------------------------------------------------

async def sintetizar(texto: str, salida: Path):
    response = await groq.audio.speech.create(
        model="playai-tts",
        voice=CONFIG.get("voz_tts", "Celeste-PlayAI"),
        input=texto,
        response_format="wav",
    )
    with open(salida, "wb") as f:
        f.write(response.read())
    log.info(f"TTS generado: {salida}")

# ---------------------------------------------------------------------------
# Estado de conversación
# ---------------------------------------------------------------------------

historiales: dict[int, list] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat_id_autorizado(chat_id: int) -> bool:
    return str(chat_id) == str(CONFIG["chat_id"])

async def responder_con_voz(context, chat_id: int, texto: str):
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "respuesta.wav"
        await sintetizar(texto, wav)
        with open(wav, "rb") as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not chat_id_autorizado(chat_id):
        log.warning(f"chat_id no autorizado: {chat_id}")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")

    with tempfile.TemporaryDirectory() as tmp:
        ogg = Path(tmp) / "entrada.ogg"
        file = await update.message.voice.get_file()
        await file.download_to_drive(ogg)

        texto = await transcribir(ogg)
        if not texto:
            await responder_con_voz(context, chat_id, "No te escuché bien, ¿podés repetir?")
            return

        historial = historiales.setdefault(chat_id, [])
        respuesta = await generar_respuesta(texto, historial)

        historial.append({"role": "user",      "content": texto})
        historial.append({"role": "assistant", "content": respuesta})

        await responder_con_voz(context, chat_id, respuesta)

async def handle_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Acepta texto — útil para testear sin grabar."""
    chat_id = update.effective_chat.id
    if not chat_id_autorizado(chat_id):
        return

    await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")

    texto    = update.message.text.strip()
    historial = historiales.setdefault(chat_id, [])
    respuesta = await generar_respuesta(texto, historial)

    historial.append({"role": "user",      "content": texto})
    historial.append({"role": "assistant", "content": respuesta})

    await responder_con_voz(context, chat_id, respuesta)

# ---------------------------------------------------------------------------
# Mensajes proactivos
# ---------------------------------------------------------------------------

async def enviar_mensaje_voz(app: Application, texto: str):
    chat_id = CONFIG["chat_id"]
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "proactivo.wav"
        await sintetizar(texto, wav)
        with open(wav, "rb") as audio:
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

    app = Application.builder().token(CONFIG["bot_token"]).build()
    app.add_handler(MessageHandler(filters.VOICE, handle_voz))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_texto))

    scheduler = AsyncIOScheduler()
    programar_recordatorios(scheduler, app)
    scheduler.start()

    log.info("Aikiu escuchando. Ctrl+C para detener.")
    await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
