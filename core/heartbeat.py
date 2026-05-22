"""
Heartbeat por rol y por instancia.

Cada bot (aikiu, familiar) llama iniciar_heartbeat(role, ...) una vez en
su main(). A partir de ahí una task asíncrona actualiza heartbeat-<role>.json
en el directorio de la instancia cada `intervalo` segundos.

El admin bot lee esos archivos y traduce el delta (now - last_seen) a un
semáforo: verde/amarillo/rojo/ausente.

Se usa un archivo por rol (heartbeat-aikiu.json, heartbeat-familiar.json)
para que los dos procesos no se pisen al escribir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from core.instance import instance_dir, instance_id
from core import state as state_mod
from core import admin_state

log = logging.getLogger("aikiu.heartbeat")

INTERVALO_DEFAULT = 60   # segundos entre escrituras de heartbeat
UMBRAL_VERDE      = 90   # < 90s desde last_seen → verde
UMBRAL_AMARILLO   = 300  # < 5min → amarillo

Estado = Literal["verde", "amarillo", "rojo", "ausente"]


def _ruta(dir_instancia: Path, role: str) -> Path:
    return dir_instancia / f"heartbeat-{role}.json"


def _escribir_atomico(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".hb.", suffix=".json.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _snapshot(role: str, started_at: str) -> dict:
    """Construye el dict que se escribe en cada tick."""
    if role == "aikiu":
        owner = state_mod.owner_chat_id()
    elif role == "familiar":
        owner = None
    elif role == "admin":
        owner = admin_state.admin_chat_id()
    else:
        owner = None
    return {
        "role": role,
        "instance_id": instance_id(),
        "pid": os.getpid(),
        "started_at": started_at,
        "last_seen": datetime.now().isoformat(timespec="seconds"),
        "owner_chat_id": owner,
    }


async def _loop(role: str, intervalo: int, started_at: str) -> None:
    path = _ruta(instance_dir(), role)
    while True:
        try:
            _escribir_atomico(path, _snapshot(role, started_at))
        except Exception as e:
            log.warning(f"heartbeat({role}): no pude escribir {path}: {e}")
        try:
            await asyncio.sleep(intervalo)
        except asyncio.CancelledError:
            break


def iniciar_heartbeat(role: str, intervalo: int = INTERVALO_DEFAULT) -> asyncio.Task:
    """
    Arranca la task de heartbeat para este proceso.

    Se llama una sola vez por main(). Devuelve el Task por si quien llama
    quiere cancelarlo durante el shutdown (opcional: cuando el proceso
    muere la task muere con él).

    Escribe un primer snapshot inmediatamente para que el admin lo vea
    sin esperar el primer tick.
    """
    started_at = datetime.now().isoformat(timespec="seconds")
    # primer snapshot sincrónico para no tener gap inicial
    try:
        _escribir_atomico(_ruta(instance_dir(), role), _snapshot(role, started_at))
    except Exception as e:
        log.warning(f"heartbeat({role}): no pude escribir snapshot inicial: {e}")
    task = asyncio.create_task(_loop(role, intervalo, started_at))
    log.info(f"heartbeat({role}) iniciado: intervalo={intervalo}s")
    return task


def leer_heartbeat(dir_instancia: Path, role: str) -> Optional[dict]:
    """Lee heartbeat-<role>.json de una instancia. None si no existe o está roto."""
    path = _ruta(dir_instancia, role)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def leer_heartbeats(dir_instancia: Path) -> dict[str, Optional[dict]]:
    """Devuelve {'aikiu': hb|None, 'familiar': hb|None} para una instancia."""
    return {
        "aikiu": leer_heartbeat(dir_instancia, "aikiu"),
        "familiar": leer_heartbeat(dir_instancia, "familiar"),
    }


def estado(hb: Optional[dict], now: Optional[datetime] = None) -> Estado:
    """Traduce un heartbeat a semáforo."""
    if not hb or not hb.get("last_seen"):
        return "ausente"
    try:
        last = datetime.fromisoformat(hb["last_seen"])
    except (ValueError, TypeError):
        return "ausente"
    delta = ((now or datetime.now()) - last).total_seconds()
    if delta < UMBRAL_VERDE:
        return "verde"
    if delta < UMBRAL_AMARILLO:
        return "amarillo"
    return "rojo"


def uptime_segundos(hb: Optional[dict], now: Optional[datetime] = None) -> Optional[int]:
    """Segundos transcurridos desde started_at, o None si no se puede calcular."""
    if not hb or not hb.get("started_at"):
        return None
    try:
        started = datetime.fromisoformat(hb["started_at"])
    except (ValueError, TypeError):
        return None
    return int(((now or datetime.now()) - started).total_seconds())


def formato_uptime(segundos: Optional[int]) -> str:
    """'2d 4h 13m' o '13m' o '—' si no hay dato."""
    if segundos is None or segundos < 0:
        return "—"
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if minutos or not partes:
        partes.append(f"{minutos}m")
    return " ".join(partes)
