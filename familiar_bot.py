"""
Bot de Telegram para familiares — gestión del perfil y alertas de Aikiu.
Cualquier familiar que mande /start queda suscripto a las alertas.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import unicodedata
import yaml
from pathlib import Path
from dotenv import load_dotenv
from groq import AsyncGroq
from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes,
)
from core.tts import sintetizar

BASE_DIR         = Path(__file__).parent
PERFIL_PATH      = BASE_DIR / "perfil.md"
FAMILIARES_PATH  = BASE_DIR / "familiares.json"
STATS_PATH       = BASE_DIR / "stats.json"

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] familiar %(message)s",
)
log = logging.getLogger("aikiu-familiar")

FAMILIAR_TOKEN = os.environ.get("FAMILIAR_BOT_TOKEN", "")
ADULTO_BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADULTO_CHAT_ID   = os.environ.get("CHAT_ID", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")

def _cargar_config():
    cfg_path = BASE_DIR / "config.yml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _cargar_voz():
    return _cargar_config().get("voz_tts", "es-AR-ElenaNeural")

def _nombre_adulto() -> str:
    return _cargar_config().get("nombre_adulto_mayor", "Marta")

VOZ_TTS = _cargar_voz()

ELIGIENDO, RECIBIENDO, ESPERANDO_MENSAJE = range(3)

SECCIONES = [
    "Quién es",
    "Familia y contactos cercanos",
    "Gustos y temas que la alegran",
    "Salud (para contexto, no para diagnosticar)",
    "Temas a manejar con cuidado",
    "Reglas del asistente",
]

# ---------------------------------------------------------------------------
# Familiares (suscriptores + nombres unificados)
# ---------------------------------------------------------------------------

def cargar_familiares() -> list[dict]:
    if FAMILIARES_PATH.exists():
        return json.loads(FAMILIARES_PATH.read_text(encoding="utf-8"))
    return []

def guardar_familiares(familiares: list[dict]):
    FAMILIARES_PATH.write_text(
        json.dumps(familiares, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def es_suscriptor(chat_id: int) -> bool:
    return any(f["chat_id"] == chat_id for f in cargar_familiares())

def agregar_familiar(chat_id: int) -> bool:
    """Agrega el familiar si no estaba. Retorna True si era nuevo."""
    familiares = cargar_familiares()
    if not any(f["chat_id"] == chat_id for f in familiares):
        familiares.append({"chat_id": chat_id, "nombre": ""})
        guardar_familiares(familiares)
        return True
    return False

def actualizar_nombre(chat_id: int, nombre: str):
    familiares = cargar_familiares()
    for f in familiares:
        if f["chat_id"] == chat_id:
            f["nombre"] = nombre.strip()
            guardar_familiares(familiares)
            return
    # Si no existe, lo agrega con nombre
    familiares.append({"chat_id": chat_id, "nombre": nombre.strip()})
    guardar_familiares(familiares)

def nombre_registrado(chat_id: int, fallback: str = "Tu familiar") -> str:
    for f in cargar_familiares():
        if f["chat_id"] == chat_id:
            return f["nombre"] or fallback
    return fallback

# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def leer_perfil() -> str:
    return PERFIL_PATH.read_text(encoding="utf-8") if PERFIL_PATH.exists() else "(Sin perfil cargado aún)"

def leer_seccion(nombre: str) -> str:
    match = re.search(
        rf'## {re.escape(nombre)}\n(.*?)(?=\n## |\Z)',
        leer_perfil(), re.DOTALL
    )
    return match.group(1).strip() if match else "(sección no encontrada)"

def actualizar_seccion(nombre: str, nuevo: str):
    nuevo_content = re.sub(
        rf'(## {re.escape(nombre)}\n)(.*?)(?=\n## |\Z)',
        lambda m: f"{m.group(1)}{nuevo.strip()}\n\n",
        leer_perfil(), flags=re.DOTALL
    )
    PERFIL_PATH.write_text(nuevo_content, encoding="utf-8")

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nuevo = agregar_familiar(chat_id)
    nombre_tg = update.effective_user.first_name or "familiar"
    adulto = _nombre_adulto()
    nombre_reg = nombre_registrado(chat_id, fallback="")
    aviso_nombre = (
        f"\n\nUsá /nombre para decirme cómo te conoce {adulto} "
        f"(ej: /nombre Germán)."
        if not nombre_reg else ""
    )
    menu = (
        f"/mensaje — enviarle un mensaje a {adulto} (texto o voz)\n"
        f"/nombre — registrar cómo te conoce {adulto}\n"
        "/perfil — ver el perfil actual\n"
        "/editar — editar una sección del perfil\n"
        "/stats — actividad de los últimos días\n"
        f"/aprendizajes — lo que Clara aprendió sobre {adulto}\n"
        "/suscriptores — ver quién recibe alertas\n"
        "/ayuda — ver esta ayuda"
    )
    if nuevo:
        log.info(f"Nuevo suscriptor: {chat_id} ({nombre_tg})")
        await update.message.reply_text(
            f"Hola {nombre_tg}, quedaste registrado para recibir alertas de Aikiu.{aviso_nombre}\n\n{menu}"
        )
    else:
        await update.message.reply_text(
            f"Hola {nombre_tg}, ya estabas registrado.{aviso_nombre}\n\n{menu}"
        )

async def cmd_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    adulto = _nombre_adulto()
    nombre = " ".join(context.args).strip() if context.args else ""
    if not nombre:
        actual = nombre_registrado(update.effective_chat.id, fallback="")
        if actual:
            await update.message.reply_text(
                f"Tu nombre para {adulto} es: *{actual}*\n\n"
                "Para cambiarlo: /nombre NuevoNombre",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "Todavía no registraste tu nombre.\n"
                "Usá: /nombre Germán"
            )
        return
    actualizar_nombre(update.effective_chat.id, nombre)
    log.info(f"Nombre registrado: {update.effective_chat.id} → '{nombre}'")
    await update.message.reply_text(
        f"Listo, cuando le mandes mensajes a {adulto} vas a aparecer como *{nombre}*.",
        parse_mode="Markdown",
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    adulto = _nombre_adulto()
    await update.message.reply_text(
        "*Comandos disponibles:*\n\n"
        f"/mensaje — enviarle un mensaje a {adulto} (texto o nota de voz)\n"
        f"/nombre — registrar cómo te conoce {adulto}\n"
        "/perfil — ver el perfil completo\n"
        "/editar — editar una sección del perfil\n"
        "/stats — actividad de los últimos días\n"
        f"/aprendizajes — lo que Clara aprendió sobre {adulto}\n"
        "/suscriptores — lista de familiares registrados\n"
        "/cancelar — cancela la operación en curso",
        parse_mode="Markdown"
    )

async def cmd_suscriptores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    familiares = cargar_familiares()
    if not familiares:
        await update.message.reply_text("No hay familiares registrados.")
        return
    lineas = []
    for f in familiares:
        nombre = f["nombre"] or "(sin nombre)"
        lineas.append(f"• {nombre} — ID: {f['chat_id']}")
    await update.message.reply_text(
        f"*Familiares registrados: {len(familiares)}*\n\n" + "\n".join(lineas),
        parse_mode="Markdown"
    )

async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    perfil = leer_perfil()
    for i in range(0, len(perfil), 4000):
        await update.message.reply_text(f"```\n{perfil[i:i+4000]}\n```", parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    adulto = _nombre_adulto()
    if not STATS_PATH.exists():
        await update.message.reply_text("Todavía no hay estadísticas registradas.")
        return
    try:
        stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        await update.message.reply_text("Error al leer las estadísticas.")
        return

    # Mostrar los últimos 7 días con datos
    dias = sorted(stats.keys(), reverse=True)[:7]
    if not dias:
        await update.message.reply_text("Sin datos aún.")
        return

    lineas = [f"📊 *Actividad de {adulto} — últimos días*\n"]
    for dia in dias:
        d = stats[dia]
        mensajes = d.get("mensajes", 0)
        primero  = d.get("primer_mensaje", "—")
        ultimo   = d.get("ultimo_mensaje", "—")
        distress = d.get("distress", {})
        alertas  = sum(int(distress.get(str(n), 0)) for n in [1, 2, 3])
        an       = d.get("analisis_nocturno", {})
        aprendizajes = an.get("aprendizajes_nuevos", "—")

        linea = f"📅 *{dia}*: {mensajes} msg · {primero}–{ultimo}"
        if alertas:
            linea += f" · ⚠️ {alertas} alerta(s)"
        if isinstance(aprendizajes, int) and aprendizajes > 0:
            linea += f" · 💡 {aprendizajes} aprendizaje(s)"
        lineas.append(linea)

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_aprendizajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    adulto = _nombre_adulto()
    perfil = leer_perfil()

    aprendizajes = re.search(r"## Aprendizajes\n(.*?)(?=\n## |\Z)", perfil, re.DOTALL)
    ajustes = re.search(r"## Ajustes sugeridos\n(.*?)(?=\n## |\Z)", perfil, re.DOTALL)

    texto = f"🧠 *Lo que Clara aprendió sobre {adulto}*\n\n"
    if aprendizajes and aprendizajes.group(1).strip():
        texto += aprendizajes.group(1).strip()
    else:
        texto += "_(sin aprendizajes registrados aún)_"

    if ajustes and ajustes.group(1).strip():
        texto += f"\n\n💬 *Ajustes sugeridos para la conversación*\n\n{ajustes.group(1).strip()}"

    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    keyboard = [[s] for s in SECCIONES] + [["❌ Cancelar"]]
    lista = "\n".join(f"• {s}" for s in SECCIONES)
    await update.message.reply_text(
        f"¿Qué sección querés editar? Tocá un botón o escribí el nombre exacto:\n\n{lista}",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ELIGIENDO

def _norm(s: str) -> str:
    """Normaliza texto para comparación sin tildes ni mayúsculas."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()

_SECCIONES_NORM = {_norm(s): s for s in SECCIONES}

async def elegir_seccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "❌ Cancelar":
        await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    seccion = _SECCIONES_NORM.get(_norm(texto))
    if not seccion:
        await update.message.reply_text("Elegí una opción de la lista.")
        return ELIGIENDO
    context.user_data["seccion"] = seccion
    actual = leer_seccion(texto)
    await update.message.reply_text(
        f"*Sección: {texto}*\n\nContenido actual:\n```\n{actual}\n```\n\n"
        "Enviá el nuevo contenido. Cada ítem en una línea con guión:\n"
        "`- Ítem uno`\n`- Ítem dos`\n\n/cancelar para salir sin guardar.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return RECIBIENDO

async def recibir_contenido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seccion = context.user_data["seccion"]
    actualizar_seccion(seccion, update.message.text.strip())
    log.info(f"Sección '{seccion}' actualizada por {update.effective_chat.id}")
    await update.message.reply_text(
        f"✓ *{seccion}* actualizada. Clara lo tendrá en cuenta desde la próxima conversación.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# Puente familiar (/mensaje)
# ---------------------------------------------------------------------------

async def cmd_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return ConversationHandler.END
    adulto = _nombre_adulto()
    if not ADULTO_BOT_TOKEN or not ADULTO_CHAT_ID:
        await update.message.reply_text(f"Error: BOT_TOKEN o CHAT_ID de {adulto} no configurados.")
        return ConversationHandler.END
    await update.message.reply_text(
        f"Enviá tu mensaje para {adulto} (texto o nota de voz). /cancelar para salir."
    )
    return ESPERANDO_MENSAJE

async def recibir_mensaje_familiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    adulto = _nombre_adulto()
    nombre = nombre_registrado(
        update.effective_chat.id,
        fallback=update.effective_user.first_name or "Tu familiar"
    )

    # Obtener el texto: desde voz o texto plano
    if update.message.voice:
        if not GROQ_API_KEY:
            await update.message.reply_text("Error: GROQ_API_KEY no configurada para transcribir audio.")
            return ConversationHandler.END
        try:
            groq = AsyncGroq(api_key=GROQ_API_KEY)
            with tempfile.TemporaryDirectory() as tmp:
                ogg = Path(tmp) / "familiar.ogg"
                archivo = await update.message.voice.get_file()
                await archivo.download_to_drive(ogg)
                with open(ogg, "rb") as f:
                    result = await groq.audio.transcriptions.create(
                        file=(ogg.name, f, "audio/ogg"),
                        model="whisper-large-v3",
                        language="es",
                        response_format="text",
                    )
            texto = result.strip() if isinstance(result, str) else result.text.strip()
            log.info(f"Transcripción de familiar: '{texto}'")
        except Exception as e:
            log.error(f"Error transcribiendo audio: {e}")
            await update.message.reply_text("No pude transcribir el audio. Probá mandando texto.")
            return ESPERANDO_MENSAJE
    else:
        texto = update.message.text.strip()

    if not texto:
        await update.message.reply_text("No entendí el mensaje. Intentá de nuevo.")
        return ESPERANDO_MENSAJE

    mensaje_para_adulto = f"{nombre} te manda a decir: {texto}"

    try:
        async with Bot(token=ADULTO_BOT_TOKEN) as adulto_bot:
            if update.message.voice:
                with tempfile.TemporaryDirectory() as tmp:
                    ogg = Path(tmp) / "puente.ogg"
                    await sintetizar(mensaje_para_adulto, ogg, voz=VOZ_TTS)
                    with open(ogg, "rb") as audio:
                        await adulto_bot.send_voice(chat_id=ADULTO_CHAT_ID, voice=audio)
            else:
                await adulto_bot.send_message(chat_id=ADULTO_CHAT_ID, text=mensaje_para_adulto)
        log.info(f"Mensaje de {nombre} entregado a {adulto}: '{texto[:60]}'")
        await update.message.reply_text(f"Listo, le mandé a {adulto}: \"{mensaje_para_adulto}\"")
    except Exception as e:
        log.error(f"Error enviando mensaje a {adulto}: {e}")
        await update.message.reply_text(f"Hubo un error al enviarle el mensaje a {adulto}.")

    return ConversationHandler.END

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not FAMILIAR_TOKEN:
        raise RuntimeError("Falta FAMILIAR_BOT_TOKEN en .env")

    app = Application.builder().token(FAMILIAR_TOKEN).build()

    conv_editar = ConversationHandler(
        entry_points=[CommandHandler("editar", cmd_editar)],
        states={
            ELIGIENDO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_seccion)],
            RECIBIENDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_contenido)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    conv_mensaje = ConversationHandler(
        entry_points=[CommandHandler("mensaje", cmd_mensaje)],
        states={
            ESPERANDO_MENSAJE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje_familiar),
                MessageHandler(filters.VOICE, recibir_mensaje_familiar),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("ayuda",          cmd_ayuda))
    app.add_handler(CommandHandler("nombre",         cmd_nombre))
    app.add_handler(CommandHandler("perfil",         cmd_perfil))
    app.add_handler(CommandHandler("suscriptores",   cmd_suscriptores))
    app.add_handler(CommandHandler("stats",          cmd_stats))
    app.add_handler(CommandHandler("aprendizajes",   cmd_aprendizajes))
    app.add_handler(conv_editar)
    app.add_handler(conv_mensaje)

    log.info("Bot familiar iniciando...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
