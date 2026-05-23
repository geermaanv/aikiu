"""
Catálogo de límites del free tier de Groq por modelo.

Cada entrada tiene los 4 ejes de rate-limiting que Groq aplica a la cuenta
gratuita: RPM, RPD, TPM, TPD para chat; RPM, RPD, ASH, ASD para audio.
El admin bot (admin/bot.py) usa estos valores para que /llm muestre el
cuello real cuando aparecen errores 429.

Fuente: https://console.groq.com/docs/rate-limits  (snapshot 2026-05)

Si Groq cambia las cuotas, actualizá la tabla acá y nada más: el resto
del código lee desde este diccionario. Si aparece un modelo nuevo que no
está catalogado, el admin lo muestra como "modelo no catalogado" y omite
los avisos basados en límites (el resto del reporte sigue funcionando).
"""

from __future__ import annotations

from typing import Optional

# RPM = requests per minute · RPD = requests per day
# TPM = tokens per minute   · TPD = tokens per day (None = sin tope diario explícito)
# ASH = audio seconds per hour · ASD = audio seconds per day
FREE_TIER: dict[str, dict[str, Optional[int]]] = {
    # Chat / completions
    "llama-3.3-70b-versatile":              {"rpm": 30, "rpd": 1_000,  "tpm": 12_000, "tpd": 100_000},
    "llama-3.1-8b-instant":                 {"rpm": 30, "rpd": 14_400, "tpm": 6_000,  "tpd": 500_000},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"rpm": 30, "rpd": 1_000, "tpm": 30_000, "tpd": 500_000},
    "openai/gpt-oss-120b":                  {"rpm": 30, "rpd": 1_000,  "tpm": 8_000,  "tpd": 200_000},
    "openai/gpt-oss-20b":                   {"rpm": 30, "rpd": 1_000,  "tpm": 8_000,  "tpd": 200_000},
    "openai/gpt-oss-safeguard-20b":         {"rpm": 30, "rpd": 1_000,  "tpm": 8_000,  "tpd": 200_000},
    "qwen/qwen3-32b":                       {"rpm": 60, "rpd": 1_000,  "tpm": 6_000,  "tpd": 500_000},
    "moonshotai/kimi-k2-instruct":          {"rpm": 60, "rpd": 1_000,  "tpm": 10_000, "tpd": 300_000},
    "allam-2-7b":                           {"rpm": 30, "rpd": 7_000,  "tpm": 6_000,  "tpd": 500_000},
    "meta-llama/llama-prompt-guard-2-22m":  {"rpm": 30, "rpd": 14_400, "tpm": 15_000, "tpd": 500_000},
    "meta-llama/llama-prompt-guard-2-86m":  {"rpm": 30, "rpd": 14_400, "tpm": 15_000, "tpd": 500_000},
    "groq/compound":                        {"rpm": 30, "rpd": 250,    "tpm": 70_000, "tpd": None},
    "groq/compound-mini":                   {"rpm": 30, "rpd": 250,    "tpm": 70_000, "tpd": None},

    # Audio (Whisper)
    "whisper-large-v3":                     {"rpm": 20, "rpd": 2_000, "ash": 7_200, "asd": 28_800},
    "whisper-large-v3-turbo":               {"rpm": 20, "rpd": 2_000, "ash": 7_200, "asd": 28_800},
}


def es_audio(modelo: str) -> bool:
    """True si el modelo es de transcripción (Whisper), no de chat."""
    return modelo.lower().startswith("whisper")


def limites(modelo: str) -> Optional[dict]:
    """Devuelve los límites del modelo en el free tier de Groq, o None si no está catalogado."""
    return FREE_TIER.get(modelo)


def tpd(modelo: str) -> Optional[int]:
    """Tokens-per-day del modelo en el free tier. None si no está catalogado o no aplica."""
    lim = FREE_TIER.get(modelo)
    if not lim:
        return None
    return lim.get("tpd")


def tpm(modelo: str) -> Optional[int]:
    """Tokens-per-minute del modelo (relevante para diagnosticar 429)."""
    lim = FREE_TIER.get(modelo)
    if not lim:
        return None
    return lim.get("tpm")


def rpm(modelo: str) -> Optional[int]:
    """Requests-per-minute del modelo (otro vector posible para 429)."""
    lim = FREE_TIER.get(modelo)
    if not lim:
        return None
    return lim.get("rpm")


def rpd(modelo: str) -> Optional[int]:
    """Requests-per-day del modelo."""
    lim = FREE_TIER.get(modelo)
    if not lim:
        return None
    return lim.get("rpd")
