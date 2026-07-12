"""
Modelo de "hogar" (tenant) para Aikiu multi-tenant.

Un hogar = un adulto mayor registrado por su chat_id de Telegram. Cada hogar
vive en su propio directorio bajo `instances/<chat_id>/` con:

    instances/<chat_id>/
        state.json          ← datos del hogar (alta, override de config, etc.)
        config.yml          ← (opcional) override del template global
        perfil.md           ← perfil narrativo del adulto
        stats.json          ← métricas operativas del día
        receptividad.json   ← señal de engagement por tema
        familiares.json     ← chat_ids de familiares asociados a ESTE adulto
        logs/YYYY-MM-DD.md  ← log diario
        usage.json          ← uso LLM (ya existía, ahora por hogar)
        heartbeat-*.json    ← presencia del proceso (ya existía, ahora por hogar)

Compatibilidad con instalación single-tenant:
- Si `AIKIU_REGISTRY` está seteado, los hogares viven en ese directorio.
- Si no, viven en `BASE_DIR/instances/` por default.
- `core/migrate_legacy.py` mueve la instalación vieja (state.json + co. en
  la raíz del repo) al hogar correspondiente la primera vez.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent

INSTANCES_DIR_NAME = "instances"
STATE_FILENAME = "state.json"
CONFIG_FILENAME = "config.yml"
PERFIL_FILENAME = "perfil.md"
STATS_FILENAME = "stats.json"
RECEPTIVIDAD_FILENAME = "receptividad.json"
FAMILIARES_FILENAME = "familiares.json"
LOGS_DIRNAME = "logs"

log = logging.getLogger("aikiu.hogar")


# ---------------------------------------------------------------------------
# Localización del registry
# ---------------------------------------------------------------------------

def instances_root() -> Path:
    """
    Raíz donde viven los directorios de hogares.

    - Con `AIKIU_REGISTRY` seteado: ese directorio (útil para Railway con un
      volumen montado en, p.ej., /data).
    - Sin override: `<BASE_DIR>/instances/`.
    """
    raw = os.environ.get("AIKIU_REGISTRY", "").strip()
    if raw:
        return Path(raw).expanduser()
    return BASE_DIR / INSTANCES_DIR_NAME


def hogar_dir(chat_id: int | str) -> Path:
    """Directorio del hogar identificado por `chat_id`."""
    return instances_root() / str(chat_id)


# ---------------------------------------------------------------------------
# IO de bajo nivel
# ---------------------------------------------------------------------------

def _escribir_json_atomico(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _leer_json(path: Path, default=None):
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


# ---------------------------------------------------------------------------
# CRUD de hogares
# ---------------------------------------------------------------------------

def existe_hogar(chat_id: int | str) -> bool:
    """True si el directorio del hogar existe y tiene state.json."""
    d = hogar_dir(chat_id)
    return d.is_dir() and (d / STATE_FILENAME).exists()


def crear_hogar(
    chat_id: int | str,
    *,
    nombre: Optional[str] = None,
    con_state: bool = True,
) -> Path:
    """
    Crea `instances/<chat_id>/` y devuelve su path.

    - `con_state=True` (default): además escribe un `state.json` mínimo con
      `owner_chat_id` y `registered_at`. Lo usamos cuando un /start crea
      un hogar nuevo desde cero.
    - `con_state=False`: solo crea el directorio. Lo usa la migración legacy
      para no chocar con el `state.json` que va a mover desde la raíz.

    Idempotente: si el hogar ya tiene `state.json`, no se toca.
    """
    d = hogar_dir(chat_id)
    d.mkdir(parents=True, exist_ok=True)
    if not con_state:
        return d
    state_path = d / STATE_FILENAME
    if not state_path.exists():
        estado = {
            "owner_chat_id": int(chat_id),
            "registered_at": datetime.now().isoformat(timespec="seconds"),
        }
        if nombre:
            estado["nombre_adulto"] = nombre
        _escribir_json_atomico(state_path, estado)
        log.info(f"hogar creado: chat_id={chat_id} dir={d}")
    return d


def listar_hogares() -> list[int]:
    """
    Devuelve los chat_ids (ordenados) de los hogares registrados.

    Solo considera subdirectorios cuyo nombre parsea como entero y que
    tienen `state.json` adentro. Esto evita confundir un directorio mal
    nombrado con un hogar.
    """
    root = instances_root()
    if not root.exists():
        return []
    ids: list[int] = []
    for sub in root.iterdir():
        if not sub.is_dir():
            continue
        try:
            cid = int(sub.name)
        except ValueError:
            continue
        if (sub / STATE_FILENAME).exists():
            ids.append(cid)
    return sorted(ids)


def listar_dirs_hogares() -> list[Path]:
    """Igual que `listar_hogares()` pero devuelve los `Path` directamente."""
    return [hogar_dir(cid) for cid in listar_hogares()]


def borrar_hogar(chat_id: int | str) -> bool:
    """Borra recursivamente `instances/<chat_id>/`. Devuelve True si existía."""
    d = hogar_dir(chat_id)
    if not d.exists():
        return False
    try:
        shutil.rmtree(d)
        log.warning(f"hogar borrado: chat_id={chat_id} dir={d}")
        return True
    except OSError as e:
        log.error(f"no pude borrar hogar {chat_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# Acceso a archivos por hogar
# ---------------------------------------------------------------------------

def state_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / STATE_FILENAME


def config_path(chat_id: int | str) -> Path:
    """`config.yml` opcional dentro del hogar; si no existe, se usa el global."""
    return hogar_dir(chat_id) / CONFIG_FILENAME


def perfil_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / PERFIL_FILENAME


def stats_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / STATS_FILENAME


def receptividad_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / RECEPTIVIDAD_FILENAME


def familiares_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / FAMILIARES_FILENAME


def historial_path(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / "historial.json"


def logs_dir(chat_id: int | str) -> Path:
    return hogar_dir(chat_id) / LOGS_DIRNAME


# ---------------------------------------------------------------------------
# Lectura de estado por hogar
# ---------------------------------------------------------------------------

def leer_state(chat_id: int | str) -> dict:
    """Devuelve el contenido de `state.json` del hogar, o `{}` si no existe."""
    return _leer_json(state_path(chat_id), default={})


def escribir_state(chat_id: int | str, data: dict) -> None:
    """Escribe `state.json` del hogar de forma atómica."""
    _escribir_json_atomico(state_path(chat_id), data)


def actualizar_state(chat_id: int | str, **cambios) -> dict:
    """Lee, mergea `cambios` y reescribe `state.json`. Devuelve el state final."""
    estado = leer_state(chat_id)
    estado.update(cambios)
    escribir_state(chat_id, estado)
    return estado
