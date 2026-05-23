"""
Fixtures globales y bootstrap de env para que los módulos del repo se puedan
importar limpio en cualquier test (incluso los que viven en módulos que leen
env vars en tiempo de import: admin/bot.py, familiar_bot.py, andromarta/bot.py).

Acá NO se patchea el filesystem global: cada test sigue siendo responsable de
aislar su propio estado (state.json, usage.json, etc.). Solo nos aseguramos
de que existan los tokens dummy mínimos en el entorno del proceso de tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Valores dummy: si las env vars ya existen (porque hay .env real), no se pisan.
_DUMMIES = {
    "BOT_TOKEN":             "0:dummy_bot_token_para_tests",
    "GROQ_API_KEY":          "gsk_dummy_para_tests",
    "FAMILIAR_BOT_TOKEN":    "0:dummy_familiar_token",
    "ADMIN_BOT_TOKEN":       "0:dummy_admin_token",
    "ANDROMARTA_API_ID":     "12345",
    "ANDROMARTA_API_HASH":   "dummyhashvalueforandromarta",
    "ANDROMARTA_PHONE":      "+5491100000000",
    "ANDROMARTA_AIKIU_USERNAME": "aikiu_test_bot",
}
for k, v in _DUMMIES.items():
    os.environ.setdefault(k, v)
