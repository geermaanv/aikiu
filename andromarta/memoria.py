"""
Memoria conversacional de Andromarta.

Mantiene el historial de turnos con Aikiu persistido a disco para que
Andromarta no pierda contexto al reiniciar el script.

Formato del historial: lista de {role, content, ts} donde:
- role="user" → mensaje de Aikiu (lo que recibimos)
- role="assistant" → mensaje de Andromarta (lo que generamos y enviamos)

Es contraintuitivo (Aikiu como "user" y Andromarta como "assistant"), pero es
lo correcto desde la perspectiva del LLM que está actuando como Andromarta.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core.utils import load_json

DATA_DIR = Path(__file__).parent / "data"
MEMORIA_PATH = DATA_DIR / "memoria.json"

MAX_TURNOS = 40  # se conservan en disco; al LLM se le pasan los últimos VENTANA
VENTANA = 20


def cargar_historial() -> list[dict]:
    return load_json(MEMORIA_PATH, default=[])


def guardar_historial(historial: list[dict]) -> None:
    """Guarda los últimos MAX_TURNOS para no inflar el archivo."""
    MEMORIA_PATH.write_text(
        json.dumps(historial[-MAX_TURNOS:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def agregar_turno(historial: list[dict], role: str, content: str) -> None:
    historial.append({
        "role": role,
        "content": content,
        "ts": datetime.now().isoformat(timespec="seconds"),
    })
    guardar_historial(historial)


def ventana_para_llm(historial: list[dict]) -> list[dict]:
    """Devuelve solo {role, content} de los últimos VENTANA turnos (lo que come Groq)."""
    return [{"role": h["role"], "content": h["content"]} for h in historial[-VENTANA:]]


def ultimo_turno(historial: list[dict]) -> dict | None:
    return historial[-1] if historial else None


def segundos_desde_ultimo_clara(historial: list[dict]) -> int | None:
    """Segundos desde el último mensaje recibido de Aikiu, o None si no hay."""
    for turno in reversed(historial):
        if turno["role"] == "user":
            try:
                ts = datetime.fromisoformat(turno["ts"])
                return int((datetime.now() - ts).total_seconds())
            except (ValueError, KeyError):
                return None
    return None


def reset() -> None:
    """Borra el historial. Útil para empezar una sesión limpia."""
    if MEMORIA_PATH.exists():
        MEMORIA_PATH.unlink()
