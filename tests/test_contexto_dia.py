"""
Tests del contexto del día: actualidad curada (Google News) + dólar + clima.
El job de madrugada arma la lista; el LLM cura y filtra lo angustiante; el
contexto se inyecta en la conversación (respuesta + iniciativa).
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aikiu
from core import tools


def _run(coro):
    return asyncio.run(coro)


def _mock_chat(texto):
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = texto
    c = MagicMock()
    c.chat.completions.create = AsyncMock(return_value=comp)
    return c


# --- fetch de Google News (parsing del RSS) ---

def test_titulares_google_news_parsea_y_limpia(monkeypatch):
    rss = (
        "<rss><channel>"
        "<title>Google Noticias</title>"
        "<item><title>Semifinal del Mundial hoy - La Nación</title></item>"
        "<item><title>Los Rolling Stones en Buenos Aires - Clarín</title></item>"
        "</channel></rss>"
    )
    resp = MagicMock(); resp.text = rss; resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    with patch("core.tools.httpx.AsyncClient", return_value=client):
        titulares = _run(tools.titulares_google_news())
    # descarta el título del feed y el " - Medio" del final
    assert titulares == ["Semifinal del Mundial hoy", "Los Rolling Stones en Buenos Aires"]


# --- curación (aplica el escudo) ---

def test_curar_temas_parsea_lista(monkeypatch):
    salida = "- La semifinal del Mundial es hoy\n- Los Rolling Stones en Buenos Aires\ntexto suelto"
    with patch("aikiu._chat_create", AsyncMock(return_value=_mock_chat(salida).chat.completions.create.return_value)):
        temas = _run(aikiu._curar_temas(["t1", "t2"], "generales"))
    assert temas == ["La semifinal del Mundial es hoy", "Los Rolling Stones en Buenos Aires"]


def test_curar_temas_vacio_si_no_hay_titulares():
    assert _run(aikiu._curar_temas([], "generales")) == []


# --- storage + reading (solo datos de HOY) ---

def test_contexto_solo_usa_datos_de_hoy(monkeypatch, tmp_path):
    hoy = datetime.now().strftime("%Y-%m-%d")
    g = tmp_path / "global.json"
    import json
    g.write_text(json.dumps({"fecha": hoy, "temas_generales": ["semifinal del Mundial"], "dolar": "Dólar blue $X"}))
    monkeypatch.setattr(aikiu, "_CONTEXTO_GLOBAL_PATH", g)
    monkeypatch.setattr(aikiu, "_contexto_hogar_path", lambda cid: tmp_path / "noexiste.json")
    texto = aikiu._texto_contexto_del_dia(42)
    assert "semifinal del Mundial" in texto
    assert "Dólar blue" in texto


def test_contexto_ignora_datos_viejos(monkeypatch, tmp_path):
    import json
    g = tmp_path / "global.json"
    g.write_text(json.dumps({"fecha": "2020-01-01", "temas_generales": ["viejo"], "dolar": "viejo"}))
    monkeypatch.setattr(aikiu, "_CONTEXTO_GLOBAL_PATH", g)
    monkeypatch.setattr(aikiu, "_contexto_hogar_path", lambda cid: tmp_path / "noexiste.json")
    assert aikiu._texto_contexto_del_dia(42) == ""  # datos de ayer → se ignoran


# --- orquestación del job ---

def test_actualizar_contexto_global_guarda_temas_y_dolar(monkeypatch, tmp_path):
    g = tmp_path / "global.json"
    monkeypatch.setattr(aikiu, "_CONTEXTO_GLOBAL_PATH", g)
    monkeypatch.setattr(aikiu, "titulares_google_news", AsyncMock(return_value=["t1", "t2"]))
    monkeypatch.setattr(aikiu, "_curar_temas", AsyncMock(return_value=["semifinal del Mundial"]))
    monkeypatch.setattr(aikiu, "consultar_dolar", AsyncMock(return_value="Dólar blue $1000"))
    monkeypatch.setattr(aikiu.hogar_mod, "listar_hogares", lambda: [])  # sin hogares → no itera local
    _run(aikiu.actualizar_contexto_del_dia(app=None, chat_id=None))
    import json
    data = json.loads(g.read_text())
    assert data["temas_generales"] == ["semifinal del Mundial"]
    assert data["dolar"] == "Dólar blue $1000"
    assert data["fecha"] == datetime.now().strftime("%Y-%m-%d")


# --- Regresión del beta: historial viejo tomado como vigente ---

def test_prompt_avisa_que_el_historial_puede_ser_de_otros_dias(monkeypatch):
    """Bug real (18/07): el historial persistente traía 'hoy juegan Francia y
    España' de 4 días antes y Aikiu lo repetía como si fuera hoy, además
    contradiciendo al usuario. El prompt debe avisar que el historial abarca
    varios días y que lo de hoy sale solo del contexto de actualidad."""
    capturado = {}

    async def fake_chat(**kwargs):
        capturado["messages"] = kwargs["messages"]
        comp = MagicMock()
        comp.choices = [MagicMock()]
        comp.choices[0].message.content = "ok"
        comp.usage = MagicMock(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        return comp

    monkeypatch.setattr(aikiu, "_chat_create", fake_chat)
    _run(aikiu.generar_respuesta("hola", historial=[], chat_id=None))
    sistema = " ".join(
        m["content"] for m in capturado["messages"] if m["role"] == "system"
    ).lower()
    assert "días anteriores" in sistema
    assert "siga vigente" in sistema or "no asumas" in sistema
