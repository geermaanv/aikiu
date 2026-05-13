"""
Tests unitarios para core/distress.py.
Cubren el parsing del LLM y la lógica de cooldown de alertas.
"""

from datetime import datetime, timedelta
import pytest
import core.distress as distress
from core.distress import parse_llm_response, should_send_alert, record_alert_sent


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------

def test_parse_extrae_nivel_0():
    raw = "Hola Rosa, ¿cómo estás?\nDISTRESS_LEVEL: 0"
    texto, nivel = parse_llm_response(raw)
    assert nivel == 0
    assert "Hola Rosa" in texto
    assert "DISTRESS_LEVEL" not in texto

def test_parse_extrae_nivel_1():
    raw = "Ay, entiendo que te sentís sola.\nDISTRESS_LEVEL: 1"
    texto, nivel = parse_llm_response(raw)
    assert nivel == 1
    assert "DISTRESS_LEVEL" not in texto

def test_parse_extrae_nivel_3():
    raw = "DISTRESS_LEVEL: 3\nLlamá al médico ya."
    texto, nivel = parse_llm_response(raw)
    assert nivel == 3
    assert texto == "Llamá al médico ya."

def test_parse_sin_distress_level_asume_0():
    raw = "Buenas tardes, Rosa."
    texto, nivel = parse_llm_response(raw)
    assert nivel == 0
    assert texto == "Buenas tardes, Rosa."

def test_parse_distress_level_en_medio():
    raw = "Primera oración.\nDISTRESS_LEVEL: 2\nSegunda oración."
    texto, nivel = parse_llm_response(raw)
    assert nivel == 2
    assert "Primera oración." in texto
    assert "Segunda oración." in texto
    assert "DISTRESS_LEVEL" not in texto

def test_parse_con_espacios_extra():
    raw = "Texto.\n  DISTRESS_LEVEL:  1  "
    texto, nivel = parse_llm_response(raw)
    assert nivel == 1

def test_parse_respuesta_vacia():
    texto, nivel = parse_llm_response("")
    assert nivel == 0
    assert texto == ""

def test_parse_solo_distress_line():
    texto, nivel = parse_llm_response("DISTRESS_LEVEL: 2")
    assert nivel == 2
    assert texto == ""

def test_parse_distress_inline_al_final_de_oracion():
    # Bug #1: re.match no detectaba DISTRESS_LEVEL en medio de una línea
    raw = "Estoy aquí para ti... DISTRESS_LEVEL: 1"
    texto, nivel = parse_llm_response(raw)
    assert nivel == 1
    assert "DISTRESS_LEVEL" not in texto
    assert "Estoy aquí para ti" in texto

def test_parse_distress_inline_sin_salto_de_linea():
    raw = "Qué bueno que estás bien.DISTRESS_LEVEL: 0"
    texto, nivel = parse_llm_response(raw)
    assert nivel == 0
    assert "DISTRESS_LEVEL" not in texto


# ---------------------------------------------------------------------------
# should_send_alert + record_alert_sent
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def limpiar_estado():
    """Resetea el estado global de cooldowns antes de cada test."""
    distress._last_alert_time.clear()
    yield
    distress._last_alert_time.clear()

def test_nivel_0_nunca_alerta():
    assert should_send_alert(0) is False

def test_primera_alerta_nivel_1_siempre_pasa():
    assert should_send_alert(1) is True

def test_primera_alerta_nivel_2_siempre_pasa():
    assert should_send_alert(2) is True

def test_primera_alerta_nivel_3_siempre_pasa():
    assert should_send_alert(3) is True

def test_nivel_3_ignora_cooldown():
    record_alert_sent(3)
    # Nivel 3 (emergencia) no tiene cooldown — siempre alerta
    assert should_send_alert(3) is True

def test_nivel_1_bloqueado_dentro_de_cooldown():
    record_alert_sent(1)
    assert should_send_alert(1) is False

def test_nivel_2_bloqueado_dentro_de_cooldown():
    record_alert_sent(2)
    assert should_send_alert(2) is False

def test_nivel_1_pasa_despues_de_cooldown():
    distress._last_alert_time[1] = datetime.now() - timedelta(minutes=61)
    assert should_send_alert(1) is True

def test_nivel_2_pasa_despues_de_cooldown():
    distress._last_alert_time[2] = datetime.now() - timedelta(minutes=31)
    assert should_send_alert(2) is True

def test_nivel_1_bloqueado_justo_antes_de_cooldown():
    distress._last_alert_time[1] = datetime.now() - timedelta(minutes=59)
    assert should_send_alert(1) is False

def test_cooldowns_de_distintos_niveles_son_independientes():
    record_alert_sent(1)
    # Nivel 1 bloqueado, nivel 2 libre
    assert should_send_alert(1) is False
    assert should_send_alert(2) is True
