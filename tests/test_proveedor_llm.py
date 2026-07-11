"""
Tests del despachador de proveedor LLM (`aikiu._chat_create`).

El chat puede ir por Groq (default, compat) o por OpenRouter (fase GLM).
La transcripción de voz (Whisper) va SIEMPRE por Groq, independiente del
proveedor de chat.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aikiu


def _run(coro):
    return asyncio.run(coro)


def _mock_client(texto: str = "hola") -> MagicMock:
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = texto
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


def test_default_va_por_groq(monkeypatch):
    """Sin proveedor_llm configurado, el chat va por el cliente Groq."""
    monkeypatch.delitem(aikiu.CONFIG, "proveedor_llm", raising=False)
    fake_groq = _mock_client("respuesta groq")
    fake_or = _mock_client("respuesta openrouter")
    with patch("aikiu.groq", fake_groq), patch("aikiu.openrouter", fake_or):
        r = _run(aikiu._chat_create(model="m", messages=[], max_tokens=10))
    assert r.choices[0].message.content == "respuesta groq"
    fake_or.chat.completions.create.assert_not_awaited()


def test_openrouter_despacha_y_apaga_razonamiento(monkeypatch):
    """Con proveedor openrouter, va por ese cliente y apaga el reasoning
    (GLM-5 con razonamiento deja content vacío y suma latencia)."""
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "openrouter")
    fake_groq = _mock_client("respuesta groq")
    fake_or = _mock_client("respuesta openrouter")
    with patch("aikiu.groq", fake_groq), patch("aikiu.openrouter", fake_or):
        r = _run(aikiu._chat_create(model="z-ai/glm-5", messages=[], max_tokens=10))
    assert r.choices[0].message.content == "respuesta openrouter"
    fake_groq.chat.completions.create.assert_not_awaited()
    kwargs = fake_or.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}


def test_openrouter_respeta_extra_body_explicito(monkeypatch):
    """Si el caller ya pasó extra_body, no se pisa."""
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "openrouter")
    fake_or = _mock_client()
    with patch("aikiu.openrouter", fake_or):
        _run(aikiu._chat_create(
            model="m", messages=[], extra_body={"reasoning": {"enabled": True}}
        ))
    kwargs = fake_or.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"] == {"reasoning": {"enabled": True}}


def test_generar_respuesta_usa_openrouter(monkeypatch):
    """E2E liviano: generar_respuesta con proveedor openrouter llama al
    cliente OpenRouter (devuelve el texto crudo; el caller parsea distress)."""
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "openrouter")
    fake_or = _mock_client("Hola Marta, qué lindo escucharte.\nDISTRESS_LEVEL: 0")
    fake_groq = _mock_client("no debería usarse")
    with patch("aikiu.openrouter", fake_or), patch("aikiu.groq", fake_groq):
        texto = _run(aikiu.generar_respuesta("hola", historial=[]))
    assert texto.startswith("Hola Marta")
    fake_or.chat.completions.create.assert_awaited()
    fake_groq.chat.completions.create.assert_not_awaited()
