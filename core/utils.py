"""Utilidades compartidas entre aikiu.py, familiar_bot.py y core/."""

import json
import os
import tempfile
import unicodedata
import yaml
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

DIAS_ES  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
            "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

CLIMA_KEYWORDS    = ["clima", "tiempo", "temperatura", "grados", "llueve",
                     "lluvia", "frio", "calor", "pronostico", "nublado", "viento", "humedad"]
DOLAR_KEYWORDS    = ["dolar", "cotizacion", "tipo de cambio", "cambio", "billete"]
NOTICIAS_KEYWORDS = ["noticias", "que paso", "novedades", "titulares", "hoy que"]


def norm(s: str) -> str:
    """Minúsculas sin tildes para comparación de keywords."""
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()


def load_json(path: Path, default=None):
    """Lee un archivo JSON; devuelve default si no existe o está corrupto."""
    if default is None:
        default = {}
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_text_atomic(path: Path, contenido: str) -> None:
    """
    Escribe texto a `path` de forma atómica (tmp + rename).

    Si el proceso muere a mitad de la escritura, el archivo destino
    queda como estaba (no a medio escribir). Importante para perfil.md,
    stats.json, familiares.json y cualquier archivo cuya corrupción
    rompa el funcionamiento del bot.

    `os.replace` es atómico en POSIX y en Windows (NTFS) para archivos
    en el mismo directorio.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(contenido)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_json_atomic(path: Path, data) -> None:
    """Wrapper de `write_text_atomic` para JSON con formato estándar."""
    write_text_atomic(
        path, json.dumps(data, ensure_ascii=False, indent=2)
    )


def nombre_adulto() -> str:
    """Devuelve el nombre del adulto mayor desde config.yml."""
    cfg_path = BASE_DIR / "config.yml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f).get("nombre_adulto_mayor", "Marta")
    return "Marta"


def read_section(perfil: str, seccion: str) -> str:
    """Extrae el contenido de una sección ## del perfil."""
    import re
    m = re.search(rf"## {re.escape(seccion)}\n(.*?)(?=\n## |\Z)", perfil, re.DOTALL)
    return m.group(1).strip() if m else ""


def fecha_hora_es(dt: datetime | None = None) -> str:
    """Devuelve fecha y hora en español: 'miércoles 20 de mayo de 2026, 19:14'."""
    dt = dt or datetime.now()
    return (f"{DIAS_ES[dt.weekday()]} {dt.day} de "
            f"{MESES_ES[dt.month - 1]} de {dt.year}, {dt.strftime('%H:%M')}")


def fecha_en_espanol(dt: datetime | None = None) -> str:
    """Devuelve solo la fecha en español: 'miércoles 20 de mayo'."""
    dt = dt or datetime.now()
    return f"{DIAS_ES[dt.weekday()]} {dt.day} de {MESES_ES[dt.month - 1]}"
