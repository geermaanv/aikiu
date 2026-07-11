import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Bot

from core.utils import nombre_adulto as _nombre_adulto, load_json
from core import hogar as hogar_mod

# Path legacy (raíz del repo). Solo se usa cuando no se especifica
# `adulto_chat_id`: en multi-tenant cada hogar tiene su propio
# `instances/<chat_id>/familiares.json`.
FAMILIARES_PATH = Path(__file__).parent.parent / "familiares.json"

log = logging.getLogger("aikiu")


def _distress_messages(nombre: str) -> dict[int, str]:
    return {
        1: f"🟡 {nombre} mencionó algo que podría indicar que no está del todo bien.",
        2: f"🟠 {nombre} puede no estar bien en este momento.",
        3: f"🔴 ALERTA: {nombre} puede necesitar ayuda urgente.",
    }


def _path_familiares(adulto_chat_id: Optional[int]) -> Path:
    """Resuelve dónde está el `familiares.json` del adulto.

    - Si `adulto_chat_id` se especifica: el del hogar (`instances/<id>/familiares.json`).
    - Si no: el path legacy en raíz (compat con tests viejos / single-tenant).
    """
    if adulto_chat_id is not None:
        return hogar_mod.familiares_path(adulto_chat_id)
    return FAMILIARES_PATH


def cargar_suscriptores(adulto_chat_id: Optional[int] = None) -> list[int]:
    """Lista de chat_ids de familiares asociados al adulto indicado.

    Si `adulto_chat_id` es None, se usa el `familiares.json` legacy en raíz.
    """
    path = _path_familiares(adulto_chat_id)
    return [f["chat_id"] for f in load_json(path, default=[])]


def _nombre_adulto_de(adulto_chat_id: Optional[int]) -> str:
    """Nombre del adulto: del state del hogar si existe, sino fallback al
    `nombre_adulto()` legacy que lee config.yml en raíz."""
    if adulto_chat_id is not None:
        estado = hogar_mod.leer_state(adulto_chat_id)
        nombre = estado.get("nombre_adulto_mayor") or estado.get("nombre_adulto")
        if nombre:
            return nombre
    return _nombre_adulto()


async def notify_inactividad(
    horas: int,
    ultima_actividad: datetime,
    family_bot: Bot,
    adulto_chat_id: Optional[int] = None,
) -> None:
    """Avisa a los familiares que el adulto mayor lleva N horas sin escribir."""
    nombre = _nombre_adulto_de(adulto_chat_id)
    timestamp = ultima_actividad.strftime("%H:%M del %d/%m")
    texto_horas = f"{horas} {'hora' if horas == 1 else 'horas'}"
    text = (
        f"⚠️ *Sin noticias de {nombre}*\n\n"
        f"Lleva {texto_horas} sin enviar mensajes.\n"
        f"Último mensaje registrado: {timestamp}.\n\n"
        f"Puede estar bien y simplemente no usó el bot, pero vale verificar."
    )
    suscriptores = cargar_suscriptores(adulto_chat_id)
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
    adulto_chat_id: Optional[int] = None,
    motivo: str = "",
) -> None:
    """Envía alerta a todos los familiares asociados al adulto indicado.

    `motivo` es el resumen del agente vigía (por qué se disparó la alerta);
    si viene vacío, la alerta sale igual sin esa línea (compat).

    Si `adulto_chat_id` es None, se usa el `familiares.json` legacy en raíz
    (compat con tests viejos / single-tenant).
    """
    nombre = _nombre_adulto_de(adulto_chat_id)
    timestamp = datetime.now().strftime("%H:%M")
    header = _distress_messages(nombre)[distress_level]
    motivo_linea = f"*Por qué se avisa:* {motivo}\n\n" if motivo else ""
    text = (
        f"{header}\n\n"
        f"🕐 {timestamp}\n\n"
        f"{motivo_linea}"
        f"*{nombre} dijo:* {adulto_message[:200]}\n\n"
        f"*Aikiu respondió:* {bot_response[:200]}"
    )

    suscriptores = cargar_suscriptores(adulto_chat_id)
    if not suscriptores:
        log.warning(
            f"Alerta detectada (chat_id={adulto_chat_id}) pero no hay familiares "
            f"suscriptos — pedile a alguien que mande /start al bot familiar."
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
