"""
Ciclo de conversación de Andromarta.

Una "conversación" tiene tope de N turnos totales (Aikiu + Marta combinados).
Cuando se llega a ese tope, Marta cierra con un mensaje de despedida natural
y queda en estado "cerrado": no responde más a Aikiu hasta que el scheduler
de iniciativa dispare un nuevo ciclo.

Persistido en `andromarta/data/ciclo.json` para sobrevivir reinicios del bot.

Estructura del archivo:
    {
        "abierto": true|false,
        "turnos": int,                    # turnos consumidos en el ciclo actual
        "iniciado": "2026-05-22T21:00:00" # ISO timestamp del arranque del ciclo
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from core.utils import load_json

DATA_DIR = Path(__file__).parent / "data"
CICLO_PATH = DATA_DIR / "ciclo.json"

# Tope default de turnos por ciclo (Aikiu + Marta combinados).
MAX_TURNOS_CICLO_DEFAULT = 15

log = logging.getLogger("andromarta.ciclo")


def _estado_inicial() -> dict:
    """Ciclo abierto vacío — estado válido para arranque del bot la primera vez."""
    return {
        "abierto": True,
        "turnos": 0,
        "iniciado": datetime.now().isoformat(timespec="seconds"),
    }


def cargar() -> dict:
    """Devuelve el estado del ciclo. Si no existe, devuelve uno abierto vacío."""
    estado = load_json(CICLO_PATH, default={})
    if "abierto" not in estado or "turnos" not in estado:
        nuevo = _estado_inicial()
        guardar(nuevo)
        return nuevo
    return estado


def guardar(estado: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CICLO_PATH.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def esta_cerrado(estado: dict | None = None) -> bool:
    if estado is None:
        estado = cargar()
    return not estado.get("abierto", True)


def abrir_nuevo() -> dict:
    """
    Resetea el ciclo: abierto, 0 turnos consumidos.

    Lo llama el scheduler cuando dispara iniciativa (único trigger autorizado
    para reabrir, según diseño).
    """
    nuevo = _estado_inicial()
    guardar(nuevo)
    log.info("Ciclo nuevo abierto")
    return nuevo


def registrar_turno(estado: dict) -> dict:
    """Suma 1 al contador de turnos y persiste. Devuelve el estado actualizado."""
    estado["turnos"] = int(estado.get("turnos", 0)) + 1
    guardar(estado)
    return estado


def cerrar(estado: dict) -> dict:
    """Marca el ciclo como cerrado y persiste."""
    estado["abierto"] = False
    guardar(estado)
    log.info(f"Ciclo cerrado tras {estado.get('turnos', 0)} turno(s)")
    return estado


def proxima_respuesta_es_despedida(estado: dict, max_turnos: int) -> bool:
    """
    True si la próxima respuesta de Marta haría que el total LLEGUE al tope.

    Se llama DESPUÉS de haber sumado el turno entrante de Aikiu, por lo que
    `turnos` ya refleja al mensaje recién recibido. La respuesta de Marta
    sumaría 1 más; si ese total == max_turnos, es el último mensaje del ciclo
    y debe ser despedida.
    """
    return (int(estado.get("turnos", 0)) + 1) >= max_turnos
