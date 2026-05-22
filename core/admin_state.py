"""
Estado persistente del bot admin (admin_state.json).

Mismo patrón TOFU que core/state.py para el adulto, pero apuntando a
admin_chat_id. Lo mantenemos en un archivo separado de state.json porque
el dueño-adulto y el dueño-admin son personas distintas y operativamente
independientes; no quiero que un reset de uno afecte al otro.

Si la env var ADMIN_CHAT_ID está seteada, tiene prioridad (igual que
CHAT_ID en core/state.py).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
ADMIN_STATE_PATH = BASE_DIR / "admin_state.json"


def _leer_estado() -> dict:
    if not ADMIN_STATE_PATH.exists():
        return {}
    try:
        return json.loads(ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir_estado_atomico(data: dict) -> None:
    ADMIN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".admin_state.", suffix=".json.tmp", dir=str(ADMIN_STATE_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, ADMIN_STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _env_override() -> Optional[int]:
    raw = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if not raw or "PEGA_TU" in raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def admin_chat_id() -> Optional[int]:
    """Devuelve el chat_id del admin (override de .env o persistido), o None."""
    env_id = _env_override()
    if env_id is not None:
        return env_id
    estado = _leer_estado()
    valor = estado.get("admin_chat_id")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return None


def tiene_admin() -> bool:
    return admin_chat_id() is not None


def registrar_admin(chat_id) -> bool:
    """
    Registra al chat_id como admin si todavía no hay uno.
    Retorna True si quedó registrado por esta llamada, False si ya había admin.
    """
    actual = admin_chat_id()
    if actual is not None:
        return False
    if _env_override() is not None:
        return False
    estado = _leer_estado()
    estado["admin_chat_id"] = int(chat_id)
    estado["registered_at"] = datetime.now().isoformat(timespec="seconds")
    _escribir_estado_atomico(estado)
    return True


def reset_admin() -> bool:
    """Borra el admin persistido. Retorna True si había algo que borrar."""
    estado = _leer_estado()
    if "admin_chat_id" not in estado:
        return False
    estado.pop("admin_chat_id", None)
    estado.pop("registered_at", None)
    _escribir_estado_atomico(estado)
    return True


def es_admin(chat_id) -> bool:
    """True si el chat_id es el admin registrado. False si no hay admin aún."""
    actual = admin_chat_id()
    return actual is not None and int(chat_id) == int(actual)
