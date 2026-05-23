"""
Abstracción de "instancia" para soportar multi-tenant en el futuro.

Hoy todo Aikiu vive en BASE_DIR (la raíz del repo). Mañana, si querés
correr varios adultos en la misma máquina, seteás AIKIU_REGISTRY a un
directorio padre y cada deploy va a su subdir nombrado AIKIU_INSTANCE_ID.

El default mantiene compatibilidad total con la instalación actual:
- AIKIU_INSTANCE_ID por defecto "default"
- AIKIU_REGISTRY por defecto no seteado → instance_dir() = BASE_DIR

Esto permite que admin/bot.py, heartbeat y usage funcionen igual en
single-tenant y multi-tenant sin tocar el resto del código.
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent


def instance_id() -> str:
    """Identificador de esta instancia. Default 'default'."""
    return os.environ.get("AIKIU_INSTANCE_ID", "default").strip() or "default"


def _registry_dir() -> Optional[Path]:
    raw = os.environ.get("AIKIU_REGISTRY", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def instance_dir() -> Path:
    """
    Devuelve el directorio raíz de runtime de esta instancia.

    - Sin AIKIU_REGISTRY: devuelve BASE_DIR (retrocompat: el código viejo
      sigue leyendo y escribiendo en la raíz del repo).
    - Con AIKIU_REGISTRY: devuelve <registry>/<instance_id>/, creándolo
      si no existe.
    """
    registry = _registry_dir()
    if registry is None:
        return BASE_DIR
    d = registry / instance_id()
    d.mkdir(parents=True, exist_ok=True)
    return d


def descubrir_instancias() -> list[Path]:
    """
    Lista todos los directorios de instancia conocidos.

    - Sin AIKIU_REGISTRY: devuelve [BASE_DIR] (la única instancia).
    - Con AIKIU_REGISTRY: devuelve cada subdir que contenga al menos
      un heartbeat.json (señal de que algún bot la usa).
    """
    registry = _registry_dir()
    if registry is None or not registry.exists():
        return [instance_dir()]
    instancias = []
    for sub in sorted(registry.iterdir()):
        if not sub.is_dir():
            continue
        if any(sub.glob("heartbeat*.json")) or (sub / "config.yml").exists():
            instancias.append(sub)
    return instancias or [instance_dir()]


def nombre_adulto_de(dir_instancia: Path) -> str:
    """Lee config.yml de una instancia para obtener el nombre del adulto."""
    cfg_path = dir_instancia / "config.yml"
    if not cfg_path.exists():
        return dir_instancia.name
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("nombre_adulto_mayor", dir_instancia.name)
    except Exception:
        return dir_instancia.name


def id_de(dir_instancia: Path) -> str:
    """Identificador de una instancia dado su directorio."""
    if dir_instancia == BASE_DIR:
        return instance_id()
    return dir_instancia.name
