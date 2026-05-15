import json
from datetime import datetime
from pathlib import Path
from telegram import Bot

FAMILIARES_PATH = Path(__file__).parent.parent / "familiares.json"

DISTRESS_MESSAGES = {
    1: "🟡 Rosa mencionó algo que podría indicar que no está del todo bien.",
    2: "🟠 Rosa parece estar angustiada ahora mismo.",
    3: "🔴 ALERTA: Rosa puede necesitar ayuda urgente.",
}


def cargar_suscriptores() -> list[int]:
    if FAMILIARES_PATH.exists():
        familiares = json.loads(FAMILIARES_PATH.read_text(encoding="utf-8"))
        return [f["chat_id"] for f in familiares]
    return []


async def notify_inactividad(
    horas: int,
    ultima_actividad: datetime,
    family_bot: Bot,
) -> None:
    """Avisa a los familiares que Rosa lleva N horas sin escribir."""
    timestamp = ultima_actividad.strftime("%H:%M del %d/%m")
    texto_horas = f"{horas} {'hora' if horas == 1 else 'horas'}"
    text = (
        f"⚠️ *Sin noticias de Rosa*\n\n"
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
            from logging import getLogger
            getLogger("aikiu").warning(f"No se pudo enviar alerta de inactividad a {chat_id}: {e}")


async def notify_family(
    distress_level: int,
    rosa_message: str,
    bot_response: str,
    family_bot: Bot,
    family_chat_id: str,
) -> None:
    """Envía alerta a todos los familiares registrados."""
    timestamp = datetime.now().strftime("%H:%M")
    header = DISTRESS_MESSAGES[distress_level]
    text = (
        f"{header}\n\n"
        f"🕐 {timestamp}\n\n"
        f"*Rosa dijo:* {rosa_message[:200]}\n\n"
        f"*Aikiu respondió:* {bot_response[:200]}"
    )

    suscriptores = cargar_suscriptores()
    if not suscriptores and family_chat_id:
        suscriptores = [int(family_chat_id)]

    for chat_id in suscriptores:
        try:
            await family_bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            from logging import getLogger
            getLogger("aikiu").warning(f"No se pudo enviar alerta a {chat_id}: {e}")
