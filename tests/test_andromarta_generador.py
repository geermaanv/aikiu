"""Tests para andromarta/generador.py — generación de respuestas vía Groq."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from andromarta import generador as gen_mod
from andromarta import estado as estado_mod
from andromarta import memoria as memoria_mod
from andromarta import persona as persona_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(estado_mod, "ESTADO_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(estado_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", tmp_path / "memoria.json")
    monkeypatch.setattr(memoria_mod, "DATA_DIR", tmp_path)
    # Persona en fallback embebido (PERSONA_PATH apunta a un archivo inexistente)
    monkeypatch.setattr(persona_mod, "PERSONA_PATH", tmp_path / "persona.md")
    yield


def _mock_groq(respuesta: str):
    choice = MagicMock()
    choice.message.content = respuesta
    completion = MagicMock()
    completion.choices = [choice]
    groq = MagicMock()
    groq.chat.completions.create = AsyncMock(return_value=completion)
    return groq


# ---------------------------------------------------------------------------
# _limpiar_artefactos
# ---------------------------------------------------------------------------

def test_limpiar_quita_distress_level():
    assert gen_mod._limpiar_artefactos("Hola che. DISTRESS_LEVEL: 2") == "Hola che."


def test_limpiar_quita_distress_level_case_insensitive():
    assert "distress" not in gen_mod._limpiar_artefactos("texto Distress_level: 1").lower()


def test_limpiar_quita_asteriscos_markdown():
    assert gen_mod._limpiar_artefactos("**hola** *che*") == "hola che"


def test_limpiar_quita_comillas_envoltorias_dobles():
    assert gen_mod._limpiar_artefactos('"hola che"') == "hola che"


def test_limpiar_quita_comillas_envoltorias_simples():
    assert gen_mod._limpiar_artefactos("'hola che'") == "hola che"


def test_limpiar_preserva_comillas_internas():
    """Comillas internas (no envuelven) no se tocan."""
    out = gen_mod._limpiar_artefactos('me dijo "qué calor", una nena')
    assert '"qué calor"' in out


def test_limpiar_strip():
    assert gen_mod._limpiar_artefactos("   hola   ") == "hola"


# ---------------------------------------------------------------------------
# responder — flujo normal (con mensaje_de_clara)
# ---------------------------------------------------------------------------

def test_responder_con_mensaje_de_clara():
    groq = _mock_groq("¡Hola mi vida!")
    hist = [{"role": "user", "content": "Hola Marta", "ts": "x"}]
    resp = run(gen_mod.responder(
        groq=groq,
        modelo="llama-3.3-70b-versatile",
        historial=hist,
        nombre_clara="Aikiu",
        mensaje_de_clara="¿Cómo andás?",
    ))
    assert resp == "¡Hola mi vida!"
    # Se llamó a Groq con messages que incluyen el system, historial y el nuevo user
    args = groq.chat.completions.create.await_args
    msgs = args.kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "¿Cómo andás?"


def test_responder_limpia_artefactos_del_llm():
    groq = _mock_groq("Hola Aikiu.\nDISTRESS_LEVEL: 2")
    resp = run(gen_mod.responder(
        groq=groq, modelo="m", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara="hi",
    ))
    assert "DISTRESS_LEVEL" not in resp
    assert "Hola Aikiu." in resp


# ---------------------------------------------------------------------------
# responder — iniciativa (mensaje_de_clara=None)
# ---------------------------------------------------------------------------

def test_responder_iniciativa_no_agrega_user_de_clara():
    """Cuando mensaje_de_clara=None, no se agrega rol user de Aikiu al final,
    sino una instrucción extra de sistema."""
    groq = _mock_groq("Che, ¿cómo va?")
    resp = run(gen_mod.responder(
        groq=groq, modelo="m", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara=None,
    ))
    args = groq.chat.completions.create.await_args
    msgs = args.kwargs["messages"]
    # Último mensaje es system con instrucción de iniciativa
    assert msgs[-1]["role"] == "system"
    assert "iniciativa" in msgs[-1]["content"].lower() or "espontáneamente" in msgs[-1]["content"].lower()
    assert resp == "Che, ¿cómo va?"


def test_responder_iniciativa_menciona_franja_horaria():
    groq = _mock_groq("Hola")
    run(gen_mod.responder(
        groq=groq, modelo="m", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara=None,
    ))
    msgs = groq.chat.completions.create.await_args.kwargs["messages"]
    franjas = ("mañana", "mediodía", "tarde", "noche", "madrugada")
    assert any(f in msgs[-1]["content"] for f in franjas)


# ---------------------------------------------------------------------------
# responder — despedida
# ---------------------------------------------------------------------------

def test_responder_despedida_agrega_instruccion_de_cierre():
    groq = _mock_groq("Bueno mi vida, te dejo que tengo que poner la pava")
    resp = run(gen_mod.responder(
        groq=groq, modelo="m", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara="hola",
        despedida=True,
    ))
    msgs = groq.chat.completions.create.await_args.kwargs["messages"]
    # El último mensaje es system con la instrucción de despedida
    assert msgs[-1]["role"] == "system"
    assert "ÚLTIMA" in msgs[-1]["content"] or "cerrar" in msgs[-1]["content"].lower()
    assert resp == "Bueno mi vida, te dejo que tengo que poner la pava"


def test_responder_no_despedida_no_agrega_instruccion_de_cierre():
    groq = _mock_groq("ok")
    run(gen_mod.responder(
        groq=groq, modelo="m", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara="hola",
        despedida=False,
    ))
    msgs = groq.chat.completions.create.await_args.kwargs["messages"]
    # No hay mensaje sobre "última respuesta"
    contenidos = " ".join(m.get("content", "") for m in msgs)
    assert "ÚLTIMA respuesta" not in contenidos


# ---------------------------------------------------------------------------
# responder — historial se respeta como ventana
# ---------------------------------------------------------------------------

def test_responder_incluye_ventana_de_historial():
    groq = _mock_groq("ok")
    hist = [
        {"role": "user",      "content": "msg vieja", "ts": "x"},
        {"role": "assistant", "content": "resp vieja", "ts": "x"},
    ]
    run(gen_mod.responder(
        groq=groq, modelo="m", historial=hist,
        nombre_clara="Aikiu", mensaje_de_clara="nuevo",
    ))
    msgs = groq.chat.completions.create.await_args.kwargs["messages"]
    contents = [m["content"] for m in msgs]
    assert "msg vieja" in contents
    assert "resp vieja" in contents
    assert "nuevo" in contents


# ---------------------------------------------------------------------------
# Parámetros a Groq
# ---------------------------------------------------------------------------

def test_responder_usa_temperature_alta_para_variedad():
    groq = _mock_groq("ok")
    run(gen_mod.responder(
        groq=groq, modelo="modelo-x", historial=[],
        nombre_clara="Aikiu", mensaje_de_clara="x",
    ))
    kwargs = groq.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "modelo-x"
    assert kwargs["max_tokens"] == 180
    assert kwargs["temperature"] >= 0.8  # andromarta usa 0.9
