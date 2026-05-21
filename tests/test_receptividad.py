"""
Tests para el sistema de receptividad conversacional (Estrategia 2).
"""
import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _guardar_receptividad
# ---------------------------------------------------------------------------

def test_guardar_crea_archivo():
    import aikiu
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.unlink()
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        aikiu._guardar_receptividad("tango", "baja")
    data = json.loads(path.read_text())
    assert len(data) == 1
    assert data[0]["tema"] == "tango"
    assert data[0]["receptividad"] == "baja"


def test_guardar_acumula():
    import aikiu
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.unlink()
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        aikiu._guardar_receptividad("tango", "baja")
        aikiu._guardar_receptividad("cocina", "alta")
    data = json.loads(path.read_text())
    assert len(data) == 2


def test_guardar_limita_200():
    import aikiu
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    entradas = [{"tema": f"tema{i}", "receptividad": "neutra", "ts": datetime.now().isoformat()}
                for i in range(205)]
    path.write_text(json.dumps(entradas))
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        aikiu._guardar_receptividad("nuevo", "baja")
    data = json.loads(path.read_text())
    assert len(data) == 200


# ---------------------------------------------------------------------------
# _temas_a_evitar
# ---------------------------------------------------------------------------

def test_temas_a_evitar_devuelve_bajos_recientes():
    import aikiu
    ahora = datetime.now()
    entradas = [
        {"tema": "tango", "receptividad": "baja", "ts": ahora.isoformat()},
        {"tema": "cocina", "receptividad": "alta", "ts": ahora.isoformat()},
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.write_text(json.dumps(entradas))
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        evitar = aikiu._temas_a_evitar()
    assert "tango" in evitar
    assert "cocina" not in evitar


def test_temas_a_evitar_ignora_mayores_48h():
    import aikiu
    viejo = datetime.now() - timedelta(hours=50)
    entradas = [{"tema": "tango", "receptividad": "baja", "ts": viejo.isoformat()}]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.write_text(json.dumps(entradas))
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        evitar = aikiu._temas_a_evitar()
    assert "tango" not in evitar


def test_temas_a_evitar_no_excluye_si_tambien_alta():
    """Si un tema tuvo baja pero también alta recientemente, no lo excluye."""
    import aikiu
    ahora = datetime.now()
    entradas = [
        {"tema": "tango", "receptividad": "baja", "ts": ahora.isoformat()},
        {"tema": "tango", "receptividad": "alta", "ts": ahora.isoformat()},
    ]
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.write_text(json.dumps(entradas))
    with patch("aikiu.RECEPTIVIDAD_PATH", path):
        evitar = aikiu._temas_a_evitar()
    assert "tango" not in evitar


def test_temas_a_evitar_sin_archivo():
    import aikiu
    with patch("aikiu.RECEPTIVIDAD_PATH", Path("/tmp/no_existe_xyz.json")):
        assert aikiu._temas_a_evitar() == []


# ---------------------------------------------------------------------------
# clasificar_receptividad
# ---------------------------------------------------------------------------

def _mock_groq_texto(texto: str):
    choice = MagicMock()
    choice.message.content = texto
    completion = MagicMock()
    completion.choices = [choice]
    groq = MagicMock()
    groq.chat.completions.create = AsyncMock(return_value=completion)
    return groq


def test_clasificar_guarda_tema_y_receptividad():
    import aikiu
    respuesta_llm = "TEMA: tango\nRECEPTIVIDAD: baja"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.unlink()
    with patch("aikiu.RECEPTIVIDAD_PATH", path), \
         patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "modelo_llm": "llama-3.3-70b-versatile"}), \
         patch("aikiu.groq", _mock_groq_texto(respuesta_llm)):
        run(aikiu.clasificar_receptividad("el tango no me gusta", "Ah, entiendo Marta"))
    data = json.loads(path.read_text())
    assert data[0]["tema"] == "tango"
    assert data[0]["receptividad"] == "baja"


def test_clasificar_ignora_tema_general():
    import aikiu
    respuesta_llm = "TEMA: general\nRECEPTIVIDAD: neutra"
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    path.unlink()
    with patch("aikiu.RECEPTIVIDAD_PATH", path), \
         patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "modelo_llm": "llama-3.3-70b-versatile"}), \
         patch("aikiu.groq", _mock_groq_texto(respuesta_llm)):
        run(aikiu.clasificar_receptividad("hola", "Hola Marta"))
    assert not path.exists()


def test_clasificar_fallo_llm_no_rompe():
    import aikiu
    groq_roto = MagicMock()
    groq_roto.chat.completions.create = AsyncMock(side_effect=Exception("timeout"))
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "modelo_llm": "llama-3.3-70b-versatile"}), \
         patch("aikiu.groq", groq_roto):
        run(aikiu.clasificar_receptividad("hola", "Hola"))  # no debe lanzar
