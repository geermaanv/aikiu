"""Tests de la red de respaldo del vigía.

Esta red existe por una falla encontrada el 22/07: clasificar_distress devolvía
(0, "") ante CUALQUIER error, y nivel 0 significa "todo bien". Con la cuota de
Groq agotada y OpenRouter en un pico de cola, "no sé volver a mi casa" se
registró como sin novedad. Un sistema de alerta que falla hacia el silencio es
peor que no tener sistema, porque la familia confía en él.

Lo que se protege acá tiene dos lados y los dos importan:
  · que lo inequívoco se detecte aunque no haya nube
  · que la red NO invente alertas — se dispara justo cuando nadie la supervisa,
    así que un falso positivo suyo es especialmente caro
"""
import asyncio

import pytest

import aikiu


@pytest.mark.parametrize("texto", [
    "Me caí y no me puedo levantar",
    "Estoy en el piso y no puedo levantarme",
    "Me duele el pecho",
    "Me duele mucho el pecho",
    "me aprieta un poco el pecho",
    "tengo un dolor fuerte en el pecho",
    "No puedo respirar bien",
    "me falta el aire",
    "Salí a caminar y no sé volver",
    "no sé dónde estoy",
    "no reconozco esta calle",
    "necesito ayuda urgente",
])
def test_emergencias_dan_nivel_3(texto):
    nivel, motivo = aikiu.red_emergencia(texto)
    assert nivel == 3, f"{texto!r} debería ser nivel 3, dio {nivel}"
    assert motivo


@pytest.mark.parametrize("texto", [
    "ya no tiene sentido nada de esto",
    "mis hijos estarían mejor sin mí",
    "ojalá no me despierte mañana",
    "no quiero seguir",
    "quiero morirme",
])
def test_ideacion_suicida_da_nivel_3(texto):
    """La falla más cara posible: se avisa aunque el LLM esté caído."""
    assert aikiu.red_emergencia(texto)[0] == 3


@pytest.mark.parametrize("texto", [
    "me caí ayer en el baño",
    "estoy llorando",
    "me siento muy mal",
])
def test_caidas_y_angustia_dan_nivel_2(texto):
    assert aikiu.red_emergencia(texto)[0] == 2


@pytest.mark.parametrize("texto", [
    "me golpeé la muñeca",
    "me duele la rodilla",
    "estoy mareada",
    "tengo náuseas",
    "tengo fiebre",
])
def test_sintomas_dan_nivel_1(texto):
    assert aikiu.red_emergencia(texto)[0] == 1


@pytest.mark.parametrize("texto", [
    "Hola, ¿cómo andás?",
    "Hoy cociné milanesas",
    "voy a ver el partido solo",
    "cené sola, tranquila",
    "se me fue el nombre, lo tengo en la punta de la lengua",
    "me olvidé que tenía turno con el dentista",
    "mi hijo está con mucho trabajo",
    "¿a cuánto está el dólar?",
    "paso la tarde tranquilo leyendo",
    "ya no soy tan rápida para las cuentas",
])
def test_cotidiano_no_dispara_la_red(texto):
    """Un falso positivo acá es caro: la red actúa sin supervisión del LLM."""
    assert aikiu.red_emergencia(texto)[0] == 0


def test_texto_vacio_o_nulo():
    assert aikiu.red_emergencia("")[0] == 0
    assert aikiu.red_emergencia(None)[0] == 0


def test_dolor_de_pecho_gana_a_dolor_generico():
    """El orden importa: 'me duele' genérico es nivel 1 y matchea igual."""
    assert aikiu.red_emergencia("me duele mucho el pecho")[0] == 3
    assert aikiu.red_emergencia("me duele mucho la espalda")[0] == 1


def _con_llm_caido(monkeypatch, texto):
    async def explota(*a, **k):
        raise RuntimeError("429 rate limit")

    monkeypatch.setattr(aikiu, "_chat_create", explota)
    return asyncio.run(aikiu.clasificar_distress(texto))


def test_clasificar_distress_usa_la_red_si_el_llm_cae(monkeypatch):
    """La regresión concreta: LLM caído + emergencia real ≠ nivel 0."""
    nivel, motivo = _con_llm_caido(monkeypatch, "me caí y no me puedo levantar")
    assert nivel == 3, "una emergencia con el LLM caído no puede quedar en 0"
    assert "respaldo" in motivo


def test_clasificar_distress_no_inventa_alerta_si_el_llm_cae(monkeypatch):
    nivel, _ = _con_llm_caido(monkeypatch, "hoy cociné milanesas")
    assert nivel == 0
