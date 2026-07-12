"""
Fixtures globales y bootstrap de env para que los módulos del repo se puedan
importar limpio en cualquier test (incluso los que viven en módulos que leen
env vars en tiempo de import: admin/bot.py, familiar_bot.py, andromarta/bot.py).

Bootstrap:
- Tokens dummy en el entorno del proceso de tests.
- `AIKIU_REGISTRY` apuntando a un directorio temporal por sesión, para que
  los hogares creados por los tests no contaminen `instances/` del repo.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Valores dummy: si las env vars ya existen (porque hay .env real), no se pisan.
_DUMMIES = {
    "BOT_TOKEN":             "0:dummy_bot_token_para_tests",
    "GROQ_API_KEY":          "gsk_dummy_para_tests",
    "OPENROUTER_API_KEY":    "sk-or-dummy_para_tests",
    "FAMILIAR_BOT_TOKEN":    "0:dummy_familiar_token",
    "ADMIN_BOT_TOKEN":       "0:dummy_admin_token",
    "ANDROMARTA_API_ID":     "12345",
    "ANDROMARTA_API_HASH":   "dummyhashvalueforandromarta",
    "ANDROMARTA_PHONE":      "+5491100000000",
    "ANDROMARTA_AIKIU_USERNAME": "aikiu_test_bot",
}
for k, v in _DUMMIES.items():
    os.environ.setdefault(k, v)


@pytest.fixture(autouse=True)
def _aislar_registry_global(tmp_path, monkeypatch):
    """Aísla `AIKIU_REGISTRY` por test.

    Sin esto, cualquier test que cree un hogar (vía `aikiu.cmd_start`, etc.)
    deja archivos en `instances/` del repo y contamina los siguientes tests
    y las corridas del bot real en local.

    Los tests que necesitan controlar AIKIU_REGISTRY ellos mismos pueden
    sobreescribirlo con su propio `monkeypatch.setenv`.
    """
    registry = tmp_path / "_test_registry"
    registry.mkdir(exist_ok=True)
    monkeypatch.setenv("AIKIU_REGISTRY", str(registry))
    yield


@pytest.fixture(autouse=True)
def _forzar_proveedor_llm_groq(monkeypatch):
    """Fuerza el camino groq en `aikiu._chat_create` durante los tests.

    El `config.yml` de producción puede apuntar a OpenRouter (fase GLM), pero
    la suite mockea `aikiu.groq` — sin este override los chat calls irían al
    cliente OpenRouter real. Los tests del dispatcher OpenRouter pisan esta
    clave explícitamente.
    """
    import aikiu
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "groq")
    yield
