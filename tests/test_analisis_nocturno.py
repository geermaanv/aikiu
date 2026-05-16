"""
Tests para el análisis nocturno: extracción de aprendizajes y ajustes de conversación.
"""
import asyncio
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


def _mock_groq(respuesta: str):
    choice = MagicMock()
    choice.message.content = respuesta
    completion = MagicMock()
    completion.choices = [choice]
    groq = MagicMock()
    groq.chat.completions.create = AsyncMock(return_value=completion)
    return groq


# ---------------------------------------------------------------------------
# _parsear_seccion
# ---------------------------------------------------------------------------

def test_parsear_aprendizajes():
    import aikiu
    texto = (
        "APRENDIZAJES_NUEVOS:\n"
        "- Le gusta la sopa de verduras\n"
        "- Mencionó que tiene frío por las noches\n"
        "AJUSTES_CONVERSACION:\n"
        "ninguno"
    )
    resultado = aikiu._parsear_seccion(texto, "APRENDIZAJES_NUEVOS")
    assert len(resultado) == 2
    assert resultado[0] == "- Le gusta la sopa de verduras"


def test_parsear_ninguno():
    import aikiu
    texto = "APRENDIZAJES_NUEVOS:\nninguno\nAJUSTES_CONVERSACION:\nninguno"
    assert aikiu._parsear_seccion(texto, "APRENDIZAJES_NUEVOS") == []
    assert aikiu._parsear_seccion(texto, "AJUSTES_CONVERSACION") == []


def test_parsear_seccion_inexistente():
    import aikiu
    assert aikiu._parsear_seccion("foo bar", "APRENDIZAJES_NUEVOS") == []


def test_parsear_ajustes():
    import aikiu
    texto = (
        "APRENDIZAJES_NUEVOS:\nninguno\n"
        "AJUSTES_CONVERSACION:\n"
        "- Evitar terminar con pregunta cuando ya se respondió\n"
    )
    resultado = aikiu._parsear_seccion(texto, "AJUSTES_CONVERSACION")
    assert len(resultado) == 1
    assert "pregunta" in resultado[0]


# ---------------------------------------------------------------------------
# analisis_nocturno — sin log
# ---------------------------------------------------------------------------

def test_sin_log_no_hace_nada():
    import aikiu
    with tempfile.TemporaryDirectory() as tmp:
        with patch("aikiu.LOGS_DIR", Path(tmp)):
            run(aikiu.analisis_nocturno())
    # No debe lanzar excepción


# ---------------------------------------------------------------------------
# analisis_nocturno — con log, escribe aprendizajes nuevos
# ---------------------------------------------------------------------------

def test_escribe_aprendizajes_nuevos():
    import aikiu
    respuesta_llm = (
        "APRENDIZAJES_NUEVOS:\n"
        "- Le gusta la sopa de verduras\n"
        "AJUSTES_CONVERSACION:\nninguno"
    )
    hoy = date.today().strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmp_logs, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_perfil:

        log_path = Path(tmp_logs) / f"{hoy}.md"
        log_path.write_text("**10:00**\n- Marta: hola\n- Clara: hola Marta\n\n")
        tmp_perfil.write("# Perfil\n\n## Aprendizajes\n- Dato viejo (01/01/2026)\n")
        tmp_perfil.flush()
        perfil_path = Path(tmp_perfil.name)

        with patch("aikiu.LOGS_DIR", Path(tmp_logs)), \
             patch("aikiu.PERFIL_PATH", perfil_path), \
             patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Clara", "modelo_llm": "llama-3.3-70b-versatile"}), \
             patch("aikiu.groq", _mock_groq(respuesta_llm)):
            run(aikiu.analisis_nocturno())

        contenido = perfil_path.read_text()
        assert "sopa de verduras" in contenido


def test_no_escribe_si_ninguno():
    import aikiu
    respuesta_llm = "APRENDIZAJES_NUEVOS:\nninguno\nAJUSTES_CONVERSACION:\nninguno"
    hoy = date.today().strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmp_logs, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_perfil:

        log_path = Path(tmp_logs) / f"{hoy}.md"
        log_path.write_text("**10:00**\n- Marta: hola\n- Clara: hola\n\n")
        contenido_original = "# Perfil\n\n## Aprendizajes\n- Dato viejo (01/01/2026)\n"
        tmp_perfil.write(contenido_original)
        tmp_perfil.flush()
        perfil_path = Path(tmp_perfil.name)

        with patch("aikiu.LOGS_DIR", Path(tmp_logs)), \
             patch("aikiu.PERFIL_PATH", perfil_path), \
             patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Clara", "modelo_llm": "llama-3.3-70b-versatile"}), \
             patch("aikiu.groq", _mock_groq(respuesta_llm)):
            run(aikiu.analisis_nocturno())

        assert perfil_path.read_text() == contenido_original


def test_escribe_ajustes_sugeridos():
    import aikiu
    respuesta_llm = (
        "APRENDIZAJES_NUEVOS:\nninguno\n"
        "AJUSTES_CONVERSACION:\n"
        "- Evitar terminar con pregunta cuando ya se respondió\n"
    )
    hoy = date.today().strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmp_logs, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_perfil:

        log_path = Path(tmp_logs) / f"{hoy}.md"
        log_path.write_text("**10:00**\n- Marta: hola\n- Clara: hola\n\n")
        tmp_perfil.write("# Perfil\n\n## Aprendizajes\n")
        tmp_perfil.flush()
        perfil_path = Path(tmp_perfil.name)

        with patch("aikiu.LOGS_DIR", Path(tmp_logs)), \
             patch("aikiu.PERFIL_PATH", perfil_path), \
             patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Clara", "modelo_llm": "llama-3.3-70b-versatile"}), \
             patch("aikiu.groq", _mock_groq(respuesta_llm)):
            run(aikiu.analisis_nocturno())

        contenido = perfil_path.read_text()
        assert "Ajustes sugeridos" in contenido
        assert "pregunta" in contenido


def test_fallo_llm_no_rompe():
    import aikiu
    hoy = date.today().strftime("%Y-%m-%d")
    groq_roto = MagicMock()
    groq_roto.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
    with tempfile.TemporaryDirectory() as tmp_logs, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_perfil:

        log_path = Path(tmp_logs) / f"{hoy}.md"
        log_path.write_text("**10:00**\n- Marta: hola\n- Clara: hola\n\n")
        tmp_perfil.write("# Perfil\n\n## Aprendizajes\n")
        tmp_perfil.flush()
        perfil_path = Path(tmp_perfil.name)

        with patch("aikiu.LOGS_DIR", Path(tmp_logs)), \
             patch("aikiu.PERFIL_PATH", perfil_path), \
             patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Clara", "modelo_llm": "llama-3.3-70b-versatile"}), \
             patch("aikiu.groq", groq_roto):
            run(aikiu.analisis_nocturno())  # no debe lanzar excepción
