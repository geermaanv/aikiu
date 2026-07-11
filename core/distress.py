import re
from datetime import datetime, timedelta
from typing import Optional

COOLDOWN_MINUTES = {1: 60, 2: 30, 3: 0}

# Cooldown indexado por (adulto_chat_id, distress_level). El cooldown es
# por hogar — una alerta nivel 2 en el hogar A no debe silenciar la
# alerta nivel 2 que el hogar B necesita en ese mismo intervalo.
# `adulto_chat_id` es None para modo legacy single-tenant (compat con
# tests viejos y deploys que aún no migraron).
_last_alert_time: dict[tuple[Optional[int], int], datetime] = {}

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


_NIVEL_RE = re.compile(r"NIVEL:\s*([0-3])")


def parse_distress_classification(raw: str) -> tuple[int, str]:
    """
    Parsea la salida del agente vigía (clasificador de distress separado).
    Espera un texto con líneas 'NIVEL: N' y opcionalmente 'MOTIVO: ...'.
    Retorna (nivel, motivo). Si no encuentra NIVEL, retorna (0, "") — nunca falla,
    para que un vigía caído no dispare una falsa alarma ni rompa la respuesta.
    """
    match = _NIVEL_RE.search(raw)
    nivel = int(match.group(1)) if match else 0
    motivo = ""
    for linea in raw.splitlines():
        if linea.strip().upper().startswith("MOTIVO:"):
            motivo = linea.split(":", 1)[1].strip()
            break
    return nivel, motivo


def should_send_alert(distress_level: int, adulto_chat_id: Optional[int] = None) -> bool:
    """
    Retorna True si corresponde enviar alerta según cooldown.

    El cooldown se aplica por (hogar, nivel). Multi-tenant: cada adulto
    tiene su propio reloj, así una alerta en un hogar no silencia otra
    en un hogar distinto.
    """
    if distress_level == 0:
        return False
    cooldown = COOLDOWN_MINUTES.get(distress_level, 60)
    if cooldown == 0:
        return True
    last = _last_alert_time.get((adulto_chat_id, distress_level))
    if last is None:
        return True
    return datetime.now() - last > timedelta(minutes=cooldown)


def record_alert_sent(distress_level: int, adulto_chat_id: Optional[int] = None) -> None:
    _last_alert_time[(adulto_chat_id, distress_level)] = datetime.now()


def reset_cooldowns() -> None:
    """Útil para tests: limpia el estado global de cooldowns."""
    _last_alert_time.clear()
