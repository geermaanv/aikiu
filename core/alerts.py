from datetime import datetime
from telegram import Bot

DISTRESS_MESSAGES = {
    1: "🟡 Rosa mencionó algo que podría indicar que no está del todo bien.",
    2: "🟠 Rosa parece estar angustiada ahora mismo.",
    3: "🔴 ALERTA: Rosa puede necesitar ayuda urgente.",
}


async def notify_family(
    distress_level: int,
    rosa_message: str,
    bot_response: str,
    family_bot: Bot,
    family_chat_id: str,
) -> None:
    """Envía alerta al familiar. Llamar solo si should_send_alert() == True."""
    timestamp = datetime.now().strftime("%H:%M")
    header = DISTRESS_MESSAGES[distress_level]

    text = (
        f"{header}\n\n"
        f"🕐 {timestamp}\n\n"
        f"*Rosa dijo:* {rosa_message[:200]}\n\n"
        f"*Aikiu respondió:* {bot_response[:200]}"
    )

    await family_bot.send_message(
        chat_id=family_chat_id,
        text=text,
        parse_mode="Markdown",
    )
