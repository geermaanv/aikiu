import re
from datetime import datetime, timedelta

COOLDOWN_MINUTES = {1: 60, 2: 30, 3: 0}

_last_alert_time: dict[int, datetime] = {}

_DISTRESS_RE = re.compile(r"DISTRESS_LEVEL:\s*([0-3])")


def parse_llm_response(raw_response: str) -> tuple[str, int]:
    """
    Separa el texto visible para el adulto mayor del nivel de distress.
    Retorna (texto_limpio, distress_level).
    Elimina la etiqueta DISTRESS_LEVEL dondequiera que aparezca en la respuesta.
    Si no encuentra DISTRESS_LEVEL, retorna level=0 (nunca falla).
    """
    match = _DISTRESS_RE.search(raw_response)
    distress_level = int(match.group(1)) if match else 0
    clean = _DISTRESS_RE.sub("", raw_response)
    return clean.strip(), distress_level


def should_send_alert(distress_level: int) -> bool:
    """Retorna True si corresponde enviar alerta según cooldown."""
    if distress_level == 0:
        return False
    cooldown = COOLDOWN_MINUTES.get(distress_level, 60)
    if cooldown == 0:
        return True
    last = _last_alert_time.get(distress_level)
    if last is None:
        return True
    return datetime.now() - last > timedelta(minutes=cooldown)


def record_alert_sent(distress_level: int) -> None:
    _last_alert_time[distress_level] = datetime.now()
