import json
from datetime import datetime
from pathlib import Path
from telegram import Bot

SUBSCRIBERS_PATH = Path(__file__).parent.parent / "subscribers.json"

DISTRESS_MESSAGES = {
    1: "🟡 Rosa mencionó algo que podría indicar que no está del todo bien.",
    2: "🟠 Rosa parece estar angustiada ahora mismo.",
    3: "🔴 ALERTA: Rosa puede necesitar ayuda urgente.",
}


def cargar_suscriptores() -> list[int]:
    if SUBSCRIBERS_PATH.exists():
        return json.loads(SUBSCRIBERS_PATH.read_text(encoding="utf-8"))
    return []


async def notify_family(
    distress_level: int,
    rosa_message: str,
    bot_response: str,
    family_bot: Bot,
    family_chat_id: str,
) -> None:
    """Envía alerta a todos los suscriptores registrados."""
    timestamp = datetime.now().strftime("%H:%M")
    header = DISTRESS_MESSAGES[distress_level]
    text = (
        f"{header}\n\n"
        f"🕐 {timestamp}\n\n"
        f"*Rosa dijo:* {rosa_message[:200]}\n\n"
        f"*Aikiu respondió:* {bot_response[:200]}"
    )

    suscriptores = cargar_suscriptores()
    # Fallback al chat_id individual si no hay suscriptores registrados
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
