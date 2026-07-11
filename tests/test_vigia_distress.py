"""
Tests del agente vigía (clasificador de distress separado del conversador).
Arquitectura de dos agentes: el conversador solo conversa, el vigía clasifica.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aikiu
from core.distress import parse_distress_classification


def _run(coro):
    return asyncio.run(coro)


def _mock_vigia(texto: str) -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = texto
    completion.usage = MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


# --- parser puro ---

def test_parse_nivel_y_motivo():
    nivel, motivo = parse_distress_classification("NIVEL: 2\nMOTIVO: mencionó una caída")
    assert nivel == 2
    assert motivo == "mencionó una caída"


def test_parse_sin_nivel_devuelve_cero():
    """Un vigía caído o respuesta basura no debe disparar falsa alarma."""
    nivel, motivo = parse_distress_classification("no entendí la consigna")
    assert nivel == 0
    assert motivo == ""


def test_parse_nivel_inline_sin_motivo():
    nivel, motivo = parse_distress_classification("NIVEL: 1")
    assert nivel == 1
    assert motivo == ""


# --- vigía (llamada LLM) ---

def test_vigia_clasifica_y_devuelve_motivo(monkeypatch):
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "groq")
    fake = _mock_vigia("NIVEL: 3\nMOTIVO: dice que se cayó y no puede levantarse")
    with patch("aikiu.groq", fake):
        nivel, motivo = _run(aikiu.clasificar_distress("me caí y no me puedo parar"))
    assert nivel == 3
    assert "no puede levantarse" in motivo


def test_vigia_falla_soft_ante_excepcion(monkeypatch):
    """Si el LLM del vigía tira excepción, retorna (0, '') y no rompe el turno."""
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "groq")
    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    with patch("aikiu.groq", fake):
        nivel, motivo = _run(aikiu.clasificar_distress("hola"))
    assert nivel == 0
    assert motivo == ""


def test_prompt_vigia_es_pura_y_contiene_criterios():
    p = aikiu._prompt_vigia("me siento sola", "Marta")
    assert "me siento sola" in p  # el mensaje se inyecta
    assert "NIVEL:" in p and "MOTIVO:" in p
    assert "Marta" in p


def test_conversador_ya_no_pide_distress():
    """El prompt del conversador NO debe contener la instrucción DISTRESS_LEVEL:
    esa responsabilidad se movió al vigía."""
    sp = aikiu.construir_system_prompt("", aikiu.CONFIG.get("_core", ""), "Aikiu", "Marta")
    assert "DISTRESS_LEVEL" not in sp
