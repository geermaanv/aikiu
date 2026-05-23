"""
Migración de una instalación legacy (single-tenant) al layout multi-tenant.

Antes de multi-tenant, todo Aikiu vivía en la raíz del repo:
    state.json, stats.json, perfil.md, receptividad.json, familiares.json,
    logs/, usage.json, heartbeat-*.json

A partir de multi-tenant, cada hogar vive en `instances/<chat_id>/`. La
primera vez que arranca el nuevo código, si encuentra una instalación
legacy con un `state.json` que tenga `owner_chat_id`, mueve todos esos
archivos a `instances/<owner_chat_id>/`.

Es idempotente: si ya se migró, no hace nada. Si no hay `owner_chat_id`
registrado todavía (instalación recién clonada), tampoco hace nada — los
hogares se van a crear cuando lleguen los primeros `/start`.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from core import hogar as hogar_mod

log = logging.getLogger("aikiu.migrate")

BASE_DIR = Path(__file__).parent.parent

# Mapeo de archivos legacy → nombre en la nueva ubicación dentro del hogar.
# Para los heartbeats hacemos glob aparte porque son varios.
_ARCHIVOS_A_MIGRAR = [
    ("state.json", hogar_mod.STATE_FILENAME),
    ("perfil.md", hogar_mod.PERFIL_FILENAME),
    ("stats.json", hogar_mod.STATS_FILENAME),
    ("receptividad.json", hogar_mod.RECEPTIVIDAD_FILENAME),
    ("familiares.json", hogar_mod.FAMILIARES_FILENAME),
    ("usage.json", "usage.json"),
]


def _leer_owner_legacy() -> Optional[int]:
    """
    Devuelve el chat_id del adulto registrado en el `state.json` viejo
    (raíz del repo), o None si no hay nada que migrar.

    Si la env var `CHAT_ID` está seteada y es válida, tiene prioridad sobre
    el state.json — esto cubre el caso de instalaciones que se manejaban
    con CHAT_ID en `.env` y nunca persistieron state.json.
    """
    raw = os.environ.get("CHAT_ID", "").strip()
    if raw and "PEGA_TU" not in raw:
        try:
            return int(raw)
        except ValueError:
            pass

    legacy_state = BASE_DIR / "state.json"
    if not legacy_state.exists():
        return None
    try:
        data = json.loads(legacy_state.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    valor = data.get("owner_chat_id")
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return None


def _mover_si_existe(origen: Path, destino: Path) -> bool:
    """Mueve `origen` a `destino` si origen existe y destino aún no."""
    if not origen.exists():
        return False
    if destino.exists():
        # Si ya hay algo en destino, no pisamos. La migración corrió antes
        # o el usuario armó el hogar a mano. Mejor dejarlo intacto.
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(origen), str(destino))
        log.info(f"migrate: {origen.name} → {destino}")
        return True
    except OSError as e:
        log.warning(f"migrate: no pude mover {origen}: {e}")
        return False


def _mover_logs(destino_dir: Path) -> int:
    """Mueve `logs/*.md` de la raíz al hogar. Devuelve cuántos archivos movió."""
    legacy_logs = BASE_DIR / "logs"
    if not legacy_logs.exists() or not legacy_logs.is_dir():
        return 0
    destino = destino_dir / hogar_mod.LOGS_DIRNAME
    destino.mkdir(parents=True, exist_ok=True)
    movidos = 0
    for archivo in legacy_logs.glob("*.md"):
        target = destino / archivo.name
        if target.exists():
            continue
        try:
            shutil.move(str(archivo), str(target))
            movidos += 1
        except OSError as e:
            log.warning(f"migrate: no pude mover {archivo}: {e}")
    # Si la carpeta vieja quedó vacía, la borramos para no dejar basura.
    try:
        if not any(legacy_logs.iterdir()):
            legacy_logs.rmdir()
    except OSError:
        pass
    return movidos


def _mover_heartbeats(destino_dir: Path) -> int:
    """Mueve `heartbeat-*.json` (excepto admin) de la raíz al hogar."""
    movidos = 0
    for hb in BASE_DIR.glob("heartbeat-*.json"):
        # El heartbeat de admin no se migra: el admin no es por instancia.
        if hb.name == "heartbeat-admin.json":
            continue
        target = destino_dir / hb.name
        if target.exists():
            continue
        try:
            shutil.move(str(hb), str(target))
            movidos += 1
        except OSError as e:
            log.warning(f"migrate: no pude mover {hb}: {e}")
    return movidos


def migrar_si_corresponde() -> Optional[int]:
    """
    Punto de entrada. Llamar al arranque de cualquier bot.

    Comportamiento:
    - Si ya existen hogares en `instances/`, no hace nada (asume migrado).
    - Si no hay hogares pero hay un `state.json` legacy con `owner_chat_id`,
      mueve esos archivos a `instances/<owner>/` y devuelve el chat_id.
    - Si no hay nada que migrar, devuelve None.

    Idempotente y silencioso ante fallos parciales (loguea warnings).
    """
    if hogar_mod.listar_hogares():
        return None

    owner = _leer_owner_legacy()
    if owner is None:
        return None

    log.warning(
        f"migrate: detectada instalación legacy con owner_chat_id={owner}. "
        f"Migrando a instances/{owner}/..."
    )
    # Sin generar state.json todavía: si hay legacy state.json lo vamos a mover.
    destino = hogar_mod.crear_hogar(owner, con_state=False)

    for legacy_name, nuevo_name in _ARCHIVOS_A_MIGRAR:
        _mover_si_existe(BASE_DIR / legacy_name, destino / nuevo_name)

    n_logs = _mover_logs(destino)
    n_hbs = _mover_heartbeats(destino)

    # Mover también los archivos rotados de usage (usage.YYYY-MM.json)
    for u in BASE_DIR.glob("usage.*.json"):
        _mover_si_existe(u, destino / u.name)

    # Si después de mover todo no quedó un state.json (caso CHAT_ID en env sin
    # state.json persistido), escribimos uno mínimo para que el hogar quede
    # detectable por `listar_hogares()`. Si sí quedó uno (lo movimos de
    # legacy), le agregamos la marca de migración para que `/hogares` pueda
    # identificarlo.
    state_destino = destino / hogar_mod.STATE_FILENAME
    if not state_destino.exists():
        from datetime import datetime as _dt
        hogar_mod._escribir_json_atomico(state_destino, {
            "owner_chat_id": owner,
            "registered_at": _dt.now().isoformat(timespec="seconds"),
            "migrated_from_legacy": True,
        })
    else:
        try:
            data = json.loads(state_destino.read_text(encoding="utf-8"))
            if isinstance(data, dict) and not data.get("migrated_from_legacy"):
                data["migrated_from_legacy"] = True
                hogar_mod._escribir_json_atomico(state_destino, data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning(f"migrate: no pude marcar migrated_from_legacy en {state_destino}: {e}")

    log.warning(
        f"migrate: hogar {owner} listo. "
        f"{n_logs} log(s), {n_hbs} heartbeat(s) movidos."
    )

    return owner
