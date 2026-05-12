"""
Bot de Telegram para familiares — gestión del perfil y alertas de Aikiu.
Cualquier familiar que mande /start queda suscripto a las alertas.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes,
)

BASE_DIR        = Path(__file__).parent
PERFIL_PATH     = BASE_DIR / "perfil.md"
SUBSCRIBERS_PATH = BASE_DIR / "subscribers.json"

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] familiar %(message)s",
)
log = logging.getLogger("aikiu-familiar")

FAMILIAR_TOKEN = os.environ.get("FAMILIAR_BOT_TOKEN", "")

ELIGIENDO, RECIBIENDO = range(2)

SECCIONES = [
    "Quién es",
    "Familia y contactos cercanos",
    "Gustos y temas que la alegran",
    "Salud (para contexto, no para diagnosticar)",
    "Temas a manejar con cuidado",
    "Reglas del asistente",
]

# ---------------------------------------------------------------------------
# Suscriptores
# ---------------------------------------------------------------------------

def cargar_suscriptores() -> list[int]:
    if SUBSCRIBERS_PATH.exists():
        return json.loads(SUBSCRIBERS_PATH.read_text(encoding="utf-8"))
    return []

def guardar_suscriptores(subs: list[int]):
    SUBSCRIBERS_PATH.write_text(json.dumps(subs), encoding="utf-8")

def agregar_suscriptor(chat_id: int) -> bool:
    """Agrega chat_id si no estaba. Retorna True si era nuevo."""
    subs = cargar_suscriptores()
    if chat_id not in subs:
        subs.append(chat_id)
        guardar_suscriptores(subs)
        return True
    return False

def es_suscriptor(chat_id: int) -> bool:
    return chat_id in cargar_suscriptores()

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
    nuevo = agregar_suscriptor(chat_id)
    nombre = update.effective_user.first_name or "familiar"
    if nuevo:
        log.info(f"Nuevo suscriptor: {chat_id} ({nombre})")
        await update.message.reply_text(
            f"Hola {nombre}, quedaste registrado para recibir alertas de Aikiu.\n\n"
            "/perfil — ver el perfil actual\n"
            "/editar — editar una sección del perfil\n"
            "/suscriptores — ver quién recibe alertas\n"
            "/ayuda — ver esta ayuda"
        )
    else:
        await update.message.reply_text(
            f"Hola {nombre}, ya estabas registrado.\n\n"
            "/perfil — ver el perfil actual\n"
            "/editar — editar una sección del perfil\n"
            "/suscriptores — ver quién recibe alertas\n"
            "/ayuda — ver esta ayuda"
        )

async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    await update.message.reply_text(
        "*Comandos disponibles:*\n\n"
        "/perfil — muestra el perfil completo\n"
        "/editar — edita una sección del perfil\n"
        "/suscriptores — lista de familiares registrados\n"
        "/cancelar — cancela la edición en curso",
        parse_mode="Markdown"
    )

async def cmd_suscriptores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    subs = cargar_suscriptores()
    await update.message.reply_text(
        f"Familiares registrados: {len(subs)}\n"
        f"IDs: {', '.join(str(s) for s in subs)}"
    )

async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    perfil = leer_perfil()
    for i in range(0, len(perfil), 4000):
        await update.message.reply_text(f"```\n{perfil[i:i+4000]}\n```", parse_mode="Markdown")

async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_suscriptor(update.effective_chat.id):
        await update.message.reply_text("Mandá /start para registrarte.")
        return
    keyboard = [[s] for s in SECCIONES] + [["❌ Cancelar"]]
    await update.message.reply_text(
        "¿Qué sección querés editar?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ELIGIENDO

async def elegir_seccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "❌ Cancelar":
        await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    if texto not in SECCIONES:
        await update.message.reply_text("Elegí una opción de la lista.")
        return ELIGIENDO
    context.user_data["seccion"] = texto
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
        f"✓ *{seccion}* actualizada.\n\nReiniciá el bot principal:\n`bash start.sh`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not FAMILIAR_TOKEN:
        raise RuntimeError("Falta FAMILIAR_BOT_TOKEN en .env")

    app = Application.builder().token(FAMILIAR_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("editar", cmd_editar)],
        states={
            ELIGIENDO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_seccion)],
            RECIBIENDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_contenido)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start",        cmd_start))
    app.add_handler(CommandHandler("ayuda",        cmd_ayuda))
    app.add_handler(CommandHandler("perfil",       cmd_perfil))
    app.add_handler(CommandHandler("suscriptores", cmd_suscriptores))
    app.add_handler(conv)

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
