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


# --- P0: resiliencia (nunca dejar al usuario colgado) ---

def test_chat_create_fallback_a_groq_si_openrouter_falla(monkeypatch):
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "openrouter")
    fake_or = MagicMock()
    fake_or.chat.completions.create = AsyncMock(side_effect=RuntimeError("OR down"))
    fake_groq = _mock_client("resp groq")
    with patch("aikiu.openrouter", fake_or), patch("aikiu.groq", fake_groq):
        r = _run(aikiu._chat_create(model="z-ai/glm-5", messages=[], max_tokens=10))
    assert r.choices[0].message.content == "resp groq"
    # cayó al modelo de respaldo de Groq
    assert fake_groq.chat.completions.create.await_args.kwargs["model"] == "llama-3.3-70b-versatile"


def test_generar_respuesta_nunca_vacia_si_llm_falla(monkeypatch):
    with patch.object(aikiu, "_chat_create", AsyncMock(side_effect=RuntimeError("todo mal"))):
        r = _run(aikiu.generar_respuesta("hola", historial=[]))
    assert r  # nunca vacío
    assert "trabó" in r.lower()


def test_generar_respuesta_maneja_content_none(monkeypatch):
    fake = _mock_client(None)  # GLM a veces devuelve content=None
    with patch("aikiu.groq", fake):
        r = _run(aikiu.generar_respuesta("hola", historial=[]))
    assert r  # frase de respaldo, no crash


def test_on_error_avisa_al_usuario():
    upd = MagicMock(); upd.effective_chat.id = 42
    ctx = MagicMock(); ctx.error = RuntimeError("boom"); ctx.bot.send_message = AsyncMock()
    _run(aikiu.on_error(upd, ctx))
    ctx.bot.send_message.assert_awaited_once()
    assert "cables" in ctx.bot.send_message.await_args.kwargs["text"].lower()
