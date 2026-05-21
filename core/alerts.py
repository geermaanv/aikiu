import json
import logging
from datetime import datetime
from pathlib import Path
from telegram import Bot
from core.utils import nombre_adulto as _nombre_adulto, load_json

FAMILIARES_PATH = Path(__file__).parent.parent / "familiares.json"
log = logging.getLogger("aikiu")


def _distress_messages(nombre: str) -> dict[int, str]:
    return {
        1: f"🟡 {nombre} mencionó algo que podría indicar que no está del todo bien.",
        2: f"🟠 {nombre} parece estar angustiada ahora mismo.",
        3: f"🔴 ALERTA: {nombre} puede necesitar ayuda urgente.",
    }


def cargar_suscriptores() -> list[int]:
    return [f["chat_id"] for f in load_json(FAMILIARES_PATH, default=[])]


async def notify_inactividad(
    horas: int,
    ultima_actividad: datetime,
    family_bot: Bot,
) -> None:
    """Avisa a los familiares que el adulto mayor lleva N horas sin escribir."""
    nombre = _nombre_adulto()
    timestamp = ultima_actividad.strftime("%H:%M del %d/%m")
    texto_horas = f"{horas} {'hora' if horas == 1 else 'horas'}"
    text = (
        f"⚠️ *Sin noticias de {nombre}*\n\n"
        f"Lleva {texto_horas} sin enviar mensajes.\n"
        f"Último mensaje registrado: {timestamp}.\n\n"
        f"Puede estar bien y simplemente no usó el bot, pero vale verificar."
    )
    suscriptores = cargar_suscriptores()
    for chat_id in suscriptores:
        try:
            await family_bot.send_message(
                chat_id=chat_id, text=text, parse_mode="Markdown"
            )
        except Exception as e:
            log.warning(f"No se pudo enviar alerta de inactividad a {chat_id}: {e}")


async def notify_family(
    distress_level: int,
    adulto_message: str,
    bot_response: str,
    family_bot: Bot,
) -> None:
    """Envía alerta a todos los familiares registrados en familiares.json."""
    nombre = _nombre_adulto()
    timestamp = datetime.now().strftime("%H:%M")
    header = _distress_messages(nombre)[distress_level]
    text = (
        f"{header}\n\n"
        f"🕐 {timestamp}\n\n"
        f"*{nombre} dijo:* {adulto_message[:200]}\n\n"
        f"*Aikiu respondió:* {bot_response[:200]}"
    )

    suscriptores = cargar_suscriptores()
    if not suscriptores:
        from logging import getLogger
        getLogger("aikiu").warning(
            "Alerta detectada pero no hay familiares suscriptos al bot familiar — "
            "pedile a alguien que mande /start al bot familiar."
        )
        return

    for chat_id in suscriptores:
        try:
            await family_bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            log.warning(f"No se pudo enviar alerta a {chat_id}: {e}")
