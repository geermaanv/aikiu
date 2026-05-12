import re
from datetime import datetime, timedelta

# Cooldown por nivel (minutos). Nivel 3 = sin cooldown (emergencia).
COOLDOWN_MINUTES = {1: 60, 2: 30, 3: 0}

_last_alert_time: dict[int, datetime] = {}


def parse_llm_response(raw_response: str) -> tuple[str, int]:
    """
    Separa el texto visible para Rosa del nivel de distress.
    Retorna (texto_limpio, distress_level).
    Si no encuentra DISTRESS_LEVEL, retorna level=0 (nunca falla).
    """
    lines = raw_response.strip().split("\n")
    distress_level = 0
    clean_lines = []

    for line in lines:
        match = re.match(r"DISTRESS_LEVEL:\s*([0-3])", line.strip())
        if match:
            distress_level = int(match.group(1))
        else:
            clean_lines.append(line)

    visible_text = "\n".join(clean_lines).strip()
    return visible_text, distress_level


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
