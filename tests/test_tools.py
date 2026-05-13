"""
Tests unitarios para core/tools.py.
Cubre el dispatcher, parsing de respuestas RSS y manejo de errores HTTP.
Todas las llamadas de red están mockeadas — no se hacen requests reales.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.tools import (
    TOOLS,
    consultar_clima,
    consultar_dolar,
    consultar_noticias,
    ejecutar_tool,
)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TOOLS: estructura mínima esperada
# ---------------------------------------------------------------------------

def test_tools_tiene_tres_herramientas():
    assert len(TOOLS) == 3

def test_tools_nombres():
    nombres = {t["function"]["name"] for t in TOOLS}
    assert nombres == {"consultar_clima", "consultar_dolar", "consultar_noticias"}

def test_tools_tienen_description():
    for t in TOOLS:
        assert t["function"]["description"]


# ---------------------------------------------------------------------------
# ejecutar_tool (dispatcher)
# ---------------------------------------------------------------------------

def test_dispatcher_clima_pasa_ciudad():
    with patch("core.tools.consultar_clima", new=AsyncMock(return_value="Clima OK")) as mock:
        result = run(ejecutar_tool("consultar_clima", {"ciudad": "Córdoba"}))
    mock.assert_called_once_with("Córdoba")
    assert result == "Clima OK"

def test_dispatcher_clima_default_buenos_aires():
    with patch("core.tools.consultar_clima", new=AsyncMock(return_value="Clima OK")) as mock:
        run(ejecutar_tool("consultar_clima", {}))
    mock.assert_called_once_with("Buenos Aires")

def test_dispatcher_dolar():
    with patch("core.tools.consultar_dolar", new=AsyncMock(return_value="Dólar OK")) as mock:
        result = run(ejecutar_tool("consultar_dolar", {}))
    mock.assert_called_once()
    assert result == "Dólar OK"

def test_dispatcher_noticias_pasa_tema():
    with patch("core.tools.consultar_noticias", new=AsyncMock(return_value="Noticias OK")) as mock:
        run(ejecutar_tool("consultar_noticias", {"tema": "deporte"}))
    mock.assert_called_once_with("deporte")

def test_dispatcher_noticias_default_sin_tema():
    with patch("core.tools.consultar_noticias", new=AsyncMock(return_value="Noticias OK")) as mock:
        run(ejecutar_tool("consultar_noticias", {}))
    mock.assert_called_once_with("")

def test_dispatcher_herramienta_desconocida():
    result = run(ejecutar_tool("herramienta_inventada", {}))
    assert "no reconocida" in result


# ---------------------------------------------------------------------------
# consultar_noticias — parsing RSS
# ---------------------------------------------------------------------------

def _mock_rss_response(xml: str):
    resp = MagicMock()
    resp.text = xml
    resp.raise_for_status = MagicMock()
    client = AsyncMock()
    client.__aenter__.return_value.get = AsyncMock(return_value=resp)
    return client

def test_noticias_parsea_cdata():
    xml = (
        "<rss><channel>"
        "<title>La Nacion</title>"
        "<title><![CDATA[Primer titular]]></title>"
        "<title><![CDATA[Segundo titular]]></title>"
        "<title><![CDATA[Tercer titular]]></title>"
        "</channel></rss>"
    )
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias())
    assert "Primer titular" in result
    assert "Segundo titular" in result

def test_noticias_fallback_sin_cdata():
    xml = (
        "<rss><channel>"
        "<title>Feed</title>"
        "<title>Noticia sin CDATA uno</title>"
        "<title>Noticia sin CDATA dos</title>"
        "</channel></rss>"
    )
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias())
    assert "Noticia sin CDATA uno" in result

def test_noticias_filtra_por_tema():
    xml = (
        "<rss><channel><title>Feed</title>"
        "<title><![CDATA[Gran partido de fútbol]]></title>"
        "<title><![CDATA[Crisis económica]]></title>"
        "<title><![CDATA[Jugada del torneo]]></title>"
        "</channel></rss>"
    )
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias(tema="fútbol"))
    assert "fútbol" in result.lower()
    assert "Crisis económica" not in result

def test_noticias_sin_match_de_tema_usa_todos():
    xml = (
        "<rss><channel><title>Feed</title>"
        "<title><![CDATA[Noticia A]]></title>"
        "<title><![CDATA[Noticia B]]></title>"
        "</channel></rss>"
    )
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias(tema="tema_que_no_existe"))
    # Sin matches, vuelve a todos los títulos disponibles
    assert "Noticia A" in result or "Noticia B" in result

def test_noticias_sin_titulos_retorna_mensaje():
    xml = "<rss><channel><title>Feed</title></channel></rss>"
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias())
    assert "No encontré" in result

def test_noticias_retorna_maximo_4_titulares():
    titulos = "".join(
        f"<title><![CDATA[Titular {i}]]></title>" for i in range(1, 9)
    )
    xml = f"<rss><channel><title>Feed</title>{titulos}</channel></rss>"
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_rss_response(xml)):
        result = run(consultar_noticias())
    # Máximo 4 titulares separados por ". "
    assert result.count("Titular") <= 4


# ---------------------------------------------------------------------------
# Manejo de errores HTTP — nunca deben lanzar excepción
# ---------------------------------------------------------------------------

def _mock_error_client():
    client = AsyncMock()
    client.__aenter__.return_value.get = AsyncMock(side_effect=Exception("timeout"))
    return client

def test_clima_error_retorna_string():
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_error_client()):
        result = run(consultar_clima())
    assert isinstance(result, str)
    assert "No pude" in result

def test_dolar_error_retorna_string():
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_error_client()):
        result = run(consultar_dolar())
    assert isinstance(result, str)
    assert "No pude" in result

def test_noticias_error_retorna_string():
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_error_client()):
        result = run(consultar_noticias())
    assert isinstance(result, str)
    assert "No pude" in result
