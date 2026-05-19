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

def test_saludo_incluye_temperatura_cuando_clima_ok():
    from unittest.mock import patch, AsyncMock
    clima_ok = "Clima en Olivos, Buenos Aires: Sunny. Temperatura 20°C (sensación 18°C), humedad 55%."

    with patch("aikiu.consultar_clima", new=AsyncMock(return_value=clima_ok)), \
         patch("aikiu.sintetizar", new=AsyncMock()), \
         patch("aikiu.CONFIG", {
             "nombre_adulto_mayor": "Marta",
             "nombre_asistente": "Clara",
             "ciudad": "Olivos, Buenos Aires",
             "chat_id": "123",
             "voz_tts": "es-AR-ElenaNeural",
         }):
        from aikiu import saludo_matutino
        app = _mock_app()
        # sintetizar está mockeado; capturamos el texto generado
        textos = []
        async def capturar(texto, salida, voz):
            textos.append(texto)
            salida.touch()  # crear archivo vacío para que open() no falle
        with patch("aikiu.sintetizar", side_effect=capturar), \
             patch("builtins.open", MagicMock()):
            run(saludo_matutino(app))
        assert textos, "saludo_matutino no llamó a sintetizar"
        saludo = textos[0]
        assert "20 grados" in saludo
        assert "Marta" in saludo
        assert "Clara" in saludo

def test_saludo_sin_clima_usa_fallback():
    with patch("aikiu.consultar_clima", new=AsyncMock(side_effect=Exception("timeout"))), \
         patch("aikiu.CONFIG", {
             "nombre_adulto_mayor": "Marta",
             "nombre_asistente": "Clara",
             "ciudad": "Olivos, Buenos Aires",
             "chat_id": "123",
             "voz_tts": "es-AR-ElenaNeural",
         }):
        from aikiu import saludo_matutino
        textos = []
        async def capturar(texto, salida, voz):
            textos.append(texto)
            salida.touch()
        with patch("aikiu.sintetizar", side_effect=capturar), \
             patch("builtins.open", MagicMock()):
            run(saludo_matutino(app := _mock_app()))
        assert textos
        saludo = textos[0]
        # Sin clima, debe seguir saludando con el nombre
        assert "Marta" in saludo
        assert "Buenos días" in saludo

def test_saludo_temperatura_igual_sensacion_no_repite():
    """Si temperatura y sensación son iguales, no mencionar sensación."""
    clima_igual = "Clima en Olivos: Clear. Temperatura 22°C (sensación 22°C), humedad 40%."
    with patch("aikiu.consultar_clima", new=AsyncMock(return_value=clima_igual)), \
         patch("aikiu.CONFIG", {
             "nombre_adulto_mayor": "Marta",
             "nombre_asistente": "Clara",
             "ciudad": "Olivos, Buenos Aires",
             "chat_id": "123",
             "voz_tts": "es-AR-ElenaNeural",
         }):
        textos = []
        async def capturar(texto, salida, voz):
            textos.append(texto)
            salida.touch()
        with patch("aikiu.sintetizar", side_effect=capturar), \
             patch("builtins.open", MagicMock()):
            run(__import__("aikiu").saludo_matutino(app := _mock_app()))
        saludo = textos[0]
        assert "22 grados" in saludo
        assert "sensación" not in saludo
