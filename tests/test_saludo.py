"""
Tests para el saludo matutino dinámico con temperatura (saludo_matutino).
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


def _mock_app(chat_id="123"):
    app = MagicMock()
    app.bot.send_voice = AsyncMock()
    return app


# ---------------------------------------------------------------------------
# Extracción de temperatura del resultado de consultar_clima
# ---------------------------------------------------------------------------

def test_regex_extrae_temperatura_y_sensacion():
    resultado = "Clima en Olivos: Sunny. Temperatura 18°C (sensación 15°C), humedad 60%."
    m = re.search(r"Temperatura (\d+)°C \(sensación (\d+)°C\)", resultado)
    assert m is not None
    assert m.group(1) == "18"
    assert m.group(2) == "15"

def test_regex_extrae_temperatura_igual_sensacion():
    resultado = "Clima en Olivos: Clear. Temperatura 22°C (sensación 22°C), humedad 45%."
    m = re.search(r"Temperatura (\d+)°C \(sensación (\d+)°C\)", resultado)
    assert m.group(1) == "22"
    assert m.group(2) == "22"

def test_regex_no_matchea_sin_temperatura():
    resultado = "No pude obtener el clima en este momento."
    m = re.search(r"Temperatura (\d+)°C \(sensación (\d+)°C\)", resultado)
    assert m is None


# ---------------------------------------------------------------------------
# saludo_matutino — integración
# ---------------------------------------------------------------------------

_CONFIG_BASE = {
    "nombre_adulto_mayor": "Marta",
    "nombre_asistente": "Aikiu",
    "ciudad": "Olivos, Buenos Aires",
    "chat_id": "123",
    "voz_tts": "es-AR-ElenaNeural",
}

def _run_saludo(clima_mock, feriado_mock=""):
    """Helper: corre saludo_matutino con clima y feriado mockeados, devuelve el texto."""
    textos = []
    async def capturar(texto, salida, voz):
        textos.append(texto)
        salida.touch()
    with patch("aikiu.consultar_clima", new=AsyncMock(return_value=clima_mock)), \
         patch("aikiu.consultar_feriado", new=AsyncMock(return_value=feriado_mock)), \
         patch("aikiu.CONFIG", _CONFIG_BASE), \
         patch("aikiu.sintetizar", side_effect=capturar), \
         patch("builtins.open", MagicMock()):
        run(__import__("aikiu").saludo_matutino(_mock_app()))
    return textos[0] if textos else ""


def test_saludo_incluye_temperatura_cuando_clima_ok():
    clima_ok = "Clima en Olivos, Buenos Aires: Sunny. Temperatura 20°C (sensación 18°C), humedad 55%."
    saludo = _run_saludo(clima_ok)
    assert "20 grados" in saludo
    assert "Marta" in saludo
    assert "Aikiu" in saludo

def test_saludo_sin_clima_usa_fallback():
    textos = []
    async def capturar(texto, salida, voz):
        textos.append(texto)
        salida.touch()
    with patch("aikiu.consultar_clima", new=AsyncMock(side_effect=Exception("timeout"))), \
         patch("aikiu.consultar_feriado", new=AsyncMock(return_value="")), \
         patch("aikiu.CONFIG", _CONFIG_BASE), \
         patch("aikiu.sintetizar", side_effect=capturar), \
         patch("builtins.open", MagicMock()):
        run(__import__("aikiu").saludo_matutino(_mock_app()))
    saludo = textos[0]
    assert "Marta" in saludo
    assert "Hola" in saludo
    assert "Hoy es" in saludo

def test_fecha_en_espanol_formato():
    """fecha_en_espanol devuelve 'día_semana N de mes' en castellano."""
    from datetime import datetime
    from aikiu import fecha_en_espanol
    # miércoles 20 de mayo de 2026
    assert fecha_en_espanol(datetime(2026, 5, 20)) == "miércoles 20 de mayo"
    # domingo 1 de enero de 2023
    assert fecha_en_espanol(datetime(2023, 1, 1)) == "domingo 1 de enero"
    # sábado 31 de diciembre de 2022
    assert fecha_en_espanol(datetime(2022, 12, 31)) == "sábado 31 de diciembre"


def test_saludo_incluye_dia_y_mes():
    """El saludo debe incluir el día de la semana y el día del mes."""
    clima_ok = "Clima en Olivos: Sunny. Temperatura 18°C (sensación 16°C), humedad 60%."
    saludo = _run_saludo(clima_ok)
    from aikiu import fecha_en_espanol
    assert fecha_en_espanol() in saludo
    assert "Hoy es" in saludo
    assert "18 grados" in saludo


def test_saludo_temperatura_igual_sensacion_no_repite():
    """Si temperatura y sensación son iguales, no mencionar sensación."""
    clima_igual = "Clima en Olivos: Clear. Temperatura 22°C (sensación 22°C), humedad 40%."
    saludo = _run_saludo(clima_igual)
    assert "22 grados" in saludo
    assert "sensación" not in saludo


def test_saludo_feriado_incluye_nombre_feriado():
    """Si es feriado, el saludo menciona el nombre y avisa sobre negocios."""
    clima_ok = "Clima en Olivos: Sunny. Temperatura 15°C (sensación 13°C), humedad 70%."
    saludo = _run_saludo(clima_ok, feriado_mock="Día de la Patria")
    assert "Día de la Patria" in saludo
    assert "feriado" in saludo.lower()
    assert "bancos" in saludo.lower()


def test_saludo_sin_feriado_no_menciona_feriado():
    """Si no es feriado, el saludo no menciona la palabra feriado."""
    clima_ok = "Clima en Olivos: Sunny. Temperatura 15°C (sensación 13°C), humedad 70%."
    saludo = _run_saludo(clima_ok, feriado_mock="")
    assert "feriado" not in saludo.lower()


def test_consultar_feriado_dia_feriado():
    """Detecta correctamente un feriado argentino conocido."""
    from datetime import datetime
    from unittest.mock import AsyncMock, patch
    feriados_ar = [
        {"date": "2026-05-25", "localName": "Día de la Patria", "name": "National Day"},
    ]
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = feriados_ar
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=mock_response)
        ))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        from aikiu import consultar_feriado
        resultado = run(consultar_feriado(datetime(2026, 5, 25)))
    assert resultado == "Día de la Patria"


def test_consultar_feriado_dia_comun():
    """Devuelve cadena vacía si no es feriado."""
    from datetime import datetime
    feriados_ar = [
        {"date": "2026-05-25", "localName": "Día de la Patria", "name": "National Day"},
    ]
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = feriados_ar
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(return_value=mock_response)
        ))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        from aikiu import consultar_feriado
        resultado = run(consultar_feriado(datetime(2026, 5, 20)))
    assert resultado == ""


def test_consultar_feriado_api_falla_devuelve_vacio():
    """Si la API falla, devuelve cadena vacía sin romper."""
    from datetime import datetime
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
            get=AsyncMock(side_effect=Exception("timeout"))
        ))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
        from aikiu import consultar_feriado
        resultado = run(consultar_feriado(datetime(2026, 5, 25)))
    assert resultado == ""
