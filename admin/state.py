"""
Estado persistente del bot admin (admin/admin_state.json).

Multi-admin: hasta ADMIN_MAX_USERS chat_ids registrados (default 5).
- Cupo abierto: cada /start desde un chat distinto suma un admin nuevo
  hasta llenar el cupo. Cuando el cupo está lleno, el resto de los /start
  se rechazan en silencio (igual que en single-admin).
- Cualquiera de los admins registrados puede usar todos los comandos.

Si la env var ADMIN_CHAT_IDS está seteada (coma-separada), tiene prioridad
sobre el archivo persistido — el archivo se ignora y no se puede agregar
ni quitar admins desde los comandos del bot. Útil para equipos que prefieren
fijar la lista a mano. También se respeta el viejo ADMIN_CHAT_ID singular
por retrocompat.

Migración: archivos persistidos con el formato viejo
    {"admin_chat_id": 123, "registered_at": "..."}
se migran transparente a
    {"version": 2, "admins": [{"chat_id": 123, "registered_at": "..."}]}

Este módulo y su estado persistido viven dentro de admin/. Si existe el JSON
legacy en la raíz del repo (de la versión anterior al refactor), se migra
de forma transparente la primera vez que se accede al estado.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
ADMIN_DIR = BASE_DIR / "admin"
ADMIN_STATE_PATH = ADMIN_DIR / "admin_state.json"
LEGACY_ADMIN_STATE_PATH = BASE_DIR / "admin_state.json"

DEFAULT_ADMIN_MAX_USERS = 5

log = logging.getLogger("aikiu.admin")


# ---------------------------------------------------------------------------
# Migración del archivo legacy de la raíz al nuevo path bajo admin/
# ---------------------------------------------------------------------------

def _migrar_legacy_si_corresponde() -> None:
    """Si existe el JSON legacy en la raíz y todavía no está en admin/, lo mueve.

    Idempotente y silencioso: si ya está migrado, o el legacy no existe, o
    falla la operación, no rompe (el flujo TOFU normal cubre el caso de
    estado vacío).
    """
    if ADMIN_STATE_PATH.exists():
        return
    if not LEGACY_ADMIN_STATE_PATH.exists():
        return
    try:
        ADMIN_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        os.replace(LEGACY_ADMIN_STATE_PATH, ADMIN_STATE_PATH)
        log.info(
            f"admin_state.json migrado de {LEGACY_ADMIN_STATE_PATH} a {ADMIN_STATE_PATH}"
        )
    except OSError as e:
        log.warning(f"No pude migrar admin_state.json legacy: {e}")


# ---------------------------------------------------------------------------
# IO de bajo nivel
# ---------------------------------------------------------------------------

def _normalizar(data: dict) -> dict:
    """Acepta tanto el formato viejo (single admin) como el nuevo (lista) y
    devuelve siempre el formato nuevo, listo para usar internamente."""
    # Formato viejo: {"admin_chat_id": int, "registered_at": str}
    if "admins" not in data and "admin_chat_id" in data:
        try:
            cid = int(data["admin_chat_id"])
        except (ValueError, TypeError):
            return {"version": 2, "admins": []}
        registered_at = str(data.get("registered_at", "")) or datetime.now().isoformat(timespec="seconds")
        return {
            "version": 2,
            "admins": [{"chat_id": cid, "registered_at": registered_at}],
        }
    # Formato nuevo (o desconocido): sanitizar la lista
    admins = []
    for a in data.get("admins", []) or []:
        if not isinstance(a, dict):
            continue
        try:
            cid = int(a.get("chat_id"))
        except (ValueError, TypeError):
            continue
        entrada = {
            "chat_id": cid,
            "registered_at": str(a.get("registered_at", "")),
        }
        if "added_by" in a:
            try:
                entrada["added_by"] = int(a["added_by"])
            except (ValueError, TypeError):
                pass
        admins.append(entrada)
    return {"version": 2, "admins": admins}


def _leer_estado() -> dict:
    _migrar_legacy_si_corresponde()
    if not ADMIN_STATE_PATH.exists():
        return {"version": 2, "admins": []}
    try:
        data = json.loads(ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 2, "admins": []}
    return _normalizar(data)


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


# ---------------------------------------------------------------------------
# Env overrides
# ---------------------------------------------------------------------------

def _env_override_ids() -> Optional[list[int]]:
    """Lee ADMIN_CHAT_IDS (lista coma-separada) o ADMIN_CHAT_ID (singular,
    retrocompat). Devuelve la lista de chat_ids parseados o None si no hay
    override válido."""
    raw_lista = os.environ.get("ADMIN_CHAT_IDS", "").strip()
    if raw_lista and "PEGA_TU" not in raw_lista:
        ids = []
        for parte in raw_lista.split(","):
            p = parte.strip()
            try:
                ids.append(int(p))
            except ValueError:
                continue
        if ids:
            # Dedupe preservando orden
            vistos: set[int] = set()
            unicos = []
            for cid in ids:
                if cid not in vistos:
                    vistos.add(cid)
                    unicos.append(cid)
            return unicos
    raw_singular = os.environ.get("ADMIN_CHAT_ID", "").strip()
    if raw_singular and "PEGA_TU" not in raw_singular:
        try:
            return [int(raw_singular)]
        except ValueError:
            return None
    return None


def admins_max() -> int:
    """Cupo máximo de admins, configurable con ADMIN_MAX_USERS (default 5)."""
    raw = os.environ.get("ADMIN_MAX_USERS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_ADMIN_MAX_USERS


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def admin_chat_ids() -> list[int]:
    """Lista de chat_ids con permiso de admin (env > persistido). Vacía si no hay."""
    env_ids = _env_override_ids()
    if env_ids is not None:
        return list(env_ids)
    estado = _leer_estado()
    return [a["chat_id"] for a in estado.get("admins", [])]


def admin_chat_id() -> Optional[int]:
    """Compatibilidad con código que esperaba un único admin: devuelve el
    primero registrado, o None si no hay ninguno. Lo usa core/heartbeat.py
    para llenar el campo owner_chat_id del snapshot del admin."""
    ids = admin_chat_ids()
    return ids[0] if ids else None


def tiene_admin() -> bool:
    """True si hay al menos un admin registrado (env o persistido)."""
    return len(admin_chat_ids()) > 0


def admin_count() -> int:
    """Cantidad actual de admins registrados."""
    return len(admin_chat_ids())


def hay_cupo() -> bool:
    """True si todavía se puede sumar un admin más sin pasar admins_max()."""
    return admin_count() < admins_max()


def listar_admins() -> list[dict]:
    """Devuelve los metadatos de cada admin (chat_id, registered_at, added_by
    si aplica). Si hay env override, devuelve dicts mínimos con source='env'."""
    env_ids = _env_override_ids()
    if env_ids is not None:
        return [{"chat_id": cid, "source": "env"} for cid in env_ids]
    estado = _leer_estado()
    return list(estado.get("admins", []))


def es_admin(chat_id) -> bool:
    """True si chat_id está en la lista de admins. Acepta int o str numérico."""
    try:
        cid = int(chat_id)
    except (ValueError, TypeError):
        return False
    return cid in admin_chat_ids()


def registrar_admin(chat_id, *, added_by: Optional[int] = None) -> bool:
    """Agrega chat_id como admin si hay cupo y no es duplicado.

    Devuelve True si quedó registrado por esta llamada, False si:
      - hay env override (la lista la maneja el .env)
      - chat_id ya estaba registrado
      - cupo lleno (admins_max())
      - chat_id no parsea como entero

    `added_by` es opcional y se persiste para auditoría cuando un admin
    existente agrega a otro (hoy el flujo de /start no lo pasa porque cada
    uno se auto-registra, pero queda preparado para /agregar_admin).
    """
    if _env_override_ids() is not None:
        return False
    try:
        cid = int(chat_id)
    except (ValueError, TypeError):
        return False
    estado = _leer_estado()
    admins = estado.get("admins", [])
    if any(a["chat_id"] == cid for a in admins):
        return False
    if len(admins) >= admins_max():
        return False
    nuevo = {
        "chat_id": cid,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
    }
    if added_by is not None:
        try:
            nuevo["added_by"] = int(added_by)
        except (ValueError, TypeError):
            pass
    admins.append(nuevo)
    estado["admins"] = admins
    estado["version"] = 2
    _escribir_estado_atomico(estado)
    return True


def quitar_admin(chat_id) -> bool:
    """Quita chat_id de la lista persistida.

    Devuelve True si había algo que quitar. No se puede usar si hay env
    override (la lista la maneja el .env) y devuelve False en ese caso.
    """
    if _env_override_ids() is not None:
        return False
    try:
        cid = int(chat_id)
    except (ValueError, TypeError):
        return False
    estado = _leer_estado()
    admins = estado.get("admins", [])
    nuevos = [a for a in admins if a["chat_id"] != cid]
    if len(nuevos) == len(admins):
        return False
    estado["admins"] = nuevos
    estado["version"] = 2
    _escribir_estado_atomico(estado)
    return True


def reset_admin() -> bool:
    """Borra TODOS los admins persistidos. Útil para reanudar bootstrap.

    No afecta al env override (la lista del .env sigue ahí). Devuelve True
    si había al menos un admin para borrar."""
    estado = _leer_estado()
    if not estado.get("admins"):
        return False
    estado["admins"] = []
    estado["version"] = 2
    _escribir_estado_atomico(estado)
    return True
