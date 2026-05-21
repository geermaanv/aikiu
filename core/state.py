"""
Estado persistente de Aikiu (state.json).

Resuelve el binding del adulto mayor al bot sin que el familiar tenga que
averiguar el CHAT_ID a mano: el primer chat que mande /start queda registrado
como dueño (patrón TOFU — Trust On First Use, igual que SSH host keys).

Una vez registrado:
- El gate `chat_id_autorizado()` rechaza cualquier otro chat.
- El familiar bot lee de acá adónde enviar los mensajes del puente.

Sigue siendo compatible con CHAT_ID en .env: si está seteado, tiene prioridad
sobre lo persistido (útil para migraciones e instalaciones existentes).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
STATE_PATH = BASE_DIR / "state.json"


def _leer_estado() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir_estado_atomico(data: dict) -> None:
    """Escribe state.json de forma atómica (tmp + rename) para evitar corrupción."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".state.", suffix=".json.tmp", dir=str(STATE_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _env_override() -> Optional[int]:
    """CHAT_ID en .env tiene prioridad sobre el dueño persistido (compat)."""
    raw = os.environ.get("CHAT_ID", "").strip()
    if not raw or "PEGA_TU" in raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def owner_chat_id() -> Optional[int]:
    """Devuelve el chat_id del adulto (override de .env o persistido), o None."""
    env_id = _env_override()
    if env_id is not None:
        return env_id
    estado = _leer_estado()
    valor = estado.get("owner_chat_id")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return None


def tiene_owner() -> bool:
    return owner_chat_id() is not None


def registrar_owner(chat_id: int) -> bool:
    """
    Registra al chat_id como dueño si todavía no hay uno.
    Retorna True si quedó registrado por esta llamada, False si ya había dueño.

    No-op si el dueño actual coincide. Si hay un dueño distinto, no hace nada
    (la seguridad la enforce quien llama, comparando con `owner_chat_id()`).
    """
    actual = owner_chat_id()
    if actual is not None:
        return False

    # Si CHAT_ID viene de .env, no escribimos state.json (el .env manda).
    if _env_override() is not None:
        return False

    estado = _leer_estado()
    estado["owner_chat_id"] = int(chat_id)
    estado["registered_at"] = datetime.now().isoformat(timespec="seconds")
    _escribir_estado_atomico(estado)
    return True


def reset_owner() -> bool:
    """Borra el dueño persistido. Retorna True si había algo que borrar."""
    estado = _leer_estado()
    if "owner_chat_id" not in estado:
        return False
    estado.pop("owner_chat_id", None)
    estado.pop("registered_at", None)
    _escribir_estado_atomico(estado)
    return True


def es_owner(chat_id: int) -> bool:
    """True si el chat_id es el dueño registrado. False si no hay dueño aún."""
    actual = owner_chat_id()
    return actual is not None and int(chat_id) == int(actual)
