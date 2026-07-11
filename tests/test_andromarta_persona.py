"""Tests para andromarta/persona.py — leer perfil y armar system prompt."""

import pytest

from andromarta import persona as persona_mod


# ---------------------------------------------------------------------------
# leer_perfil
# ---------------------------------------------------------------------------

def test_leer_perfil_devuelve_fallback_si_no_existe(tmp_path, monkeypatch):
    fake = tmp_path / "persona.md"
    monkeypatch.setattr(persona_mod, "PERSONA_PATH", fake)
    perfil = persona_mod.leer_perfil()
    assert perfil == persona_mod.PERFIL_FALLBACK
    assert "78 años" in perfil


def test_leer_perfil_lee_archivo_si_existe(tmp_path, monkeypatch):
    fake = tmp_path / "persona.md"
    fake.write_text("Soy Andromarta, contenido custom.", encoding="utf-8")
    monkeypatch.setattr(persona_mod, "PERSONA_PATH", fake)
    assert persona_mod.leer_perfil() == "Soy Andromarta, contenido custom."


def test_perfil_fallback_tiene_secciones_clave():
    pf = persona_mod.PERFIL_FALLBACK
    assert "Quién soy" in pf
    assert "Cómo hablo" in pf
    assert "Mi día" in pf
    assert "Cómo respondo a Aikiu" in pf


# ---------------------------------------------------------------------------
# construir_system_prompt
# ---------------------------------------------------------------------------

def test_system_prompt_incluye_perfil():
    perfil = "## Quién soy\nMarta de 78 años."
    estado = "Tu ánimo está tranquilo hoy."
    prompt = persona_mod.construir_system_prompt(perfil, estado, "Aikiu")
    assert "Marta de 78 años" in prompt
    assert "Tu ánimo está tranquilo hoy" in prompt


def test_system_prompt_menciona_clara():
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    assert "Aikiu" in prompt


def test_system_prompt_usa_nombre_custom_de_clara():
    """El nombre custom aparece en el prompt — las menciones a 'Aikiu' en
    las reglas hardcodeadas son aceptables porque son ejemplos del manual,
    pero las menciones dirigidas al usuario actual usan el nombre custom."""
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Sofía")
    assert "Sofía" in prompt
    # El header sobre "chatea por Telegram con X" usa el nombre custom
    assert "con Sofía" in prompt


def test_system_prompt_prohibe_revelar_ia():
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    assert "NUNCA digas que sos una IA" in prompt
    assert "agente sintético" in prompt


def test_system_prompt_no_filtra_distress_level():
    """Andromarta no debe saber del DISTRESS_LEVEL — eso es del lado de Aikiu."""
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    # Aparece como término prohibido en las instrucciones, pero no como header
    # que pida emitirlo. La regla es justamente "no usar".
    assert "Sin DISTRESS_LEVEL" in prompt


def test_system_prompt_pide_voseo():
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    assert "voseo" in prompt.lower()
    assert "rioplatense" in prompt.lower()


def test_system_prompt_pide_mensajes_cortos():
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    assert "cortos" in prompt.lower() or "corto" in prompt.lower()


def test_system_prompt_incluye_fecha_y_hora():
    prompt = persona_mod.construir_system_prompt("perfil", "estado", "Aikiu")
    # fecha_hora_es() arma algo como 'jueves 22 de mayo de 2026, 22:14'
    # No nos atamos al string exacto, pero el header debe estar
    assert "Buenos Aires" in prompt
