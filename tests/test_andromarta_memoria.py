"""Tests para andromarta/memoria.py — historial conversacional persistido."""

import json
from datetime import datetime, timedelta

import pytest

from andromarta import memoria as memoria_mod


@pytest.fixture(autouse=True)
def _aislar_memoria(tmp_path, monkeypatch):
    """Apunta MEMORIA_PATH a un archivo del tmp_path para cada test."""
    fake = tmp_path / "memoria.json"
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", fake)
    monkeypatch.setattr(memoria_mod, "DATA_DIR", tmp_path)
    yield


# ---------------------------------------------------------------------------
# cargar / guardar
# ---------------------------------------------------------------------------

def test_cargar_historial_vacio_devuelve_lista_vacia():
    assert memoria_mod.cargar_historial() == []


def test_guardar_y_cargar_idempotente():
    hist = [
        {"role": "user", "content": "hola", "ts": "2026-05-22T10:00:00"},
        {"role": "assistant", "content": "buenas", "ts": "2026-05-22T10:00:05"},
    ]
    memoria_mod.guardar_historial(hist)
    assert memoria_mod.cargar_historial() == hist


def test_guardar_recorta_a_max_turnos():
    """guardar_historial trunca a los últimos MAX_TURNOS para no inflar el archivo."""
    hist = [
        {"role": "user", "content": f"msg {i}", "ts": "2026-05-22T10:00:00"}
        for i in range(memoria_mod.MAX_TURNOS + 10)
    ]
    memoria_mod.guardar_historial(hist)
    cargado = memoria_mod.cargar_historial()
    assert len(cargado) == memoria_mod.MAX_TURNOS
    # Conservó los últimos
    assert cargado[-1]["content"] == hist[-1]["content"]


# ---------------------------------------------------------------------------
# agregar_turno
# ---------------------------------------------------------------------------

def test_agregar_turno_persiste_con_timestamp():
    hist = []
    memoria_mod.agregar_turno(hist, "user", "hola")
    assert len(hist) == 1
    assert hist[0]["role"] == "user"
    assert hist[0]["content"] == "hola"
    assert "ts" in hist[0]
    # Y quedó persistido en disco
    en_disco = memoria_mod.cargar_historial()
    assert en_disco[0]["content"] == "hola"


def test_agregar_turno_apila_en_orden():
    hist = []
    memoria_mod.agregar_turno(hist, "user", "uno")
    memoria_mod.agregar_turno(hist, "assistant", "dos")
    memoria_mod.agregar_turno(hist, "user", "tres")
    assert [t["content"] for t in hist] == ["uno", "dos", "tres"]


# ---------------------------------------------------------------------------
# ventana_para_llm
# ---------------------------------------------------------------------------

def test_ventana_para_llm_solo_devuelve_role_y_content():
    hist = [
        {"role": "user", "content": "hola", "ts": "x", "extra": "y"},
    ]
    ventana = memoria_mod.ventana_para_llm(hist)
    assert ventana == [{"role": "user", "content": "hola"}]
    assert "ts" not in ventana[0]


def test_ventana_para_llm_limita_a_VENTANA_turnos():
    hist = [
        {"role": "user", "content": f"msg {i}", "ts": "x"}
        for i in range(memoria_mod.VENTANA + 5)
    ]
    ventana = memoria_mod.ventana_para_llm(hist)
    assert len(ventana) == memoria_mod.VENTANA
    # Conservó los últimos
    assert ventana[-1]["content"] == hist[-1]["content"]


def test_ventana_vacia():
    assert memoria_mod.ventana_para_llm([]) == []


# ---------------------------------------------------------------------------
# ultimo_turno
# ---------------------------------------------------------------------------

def test_ultimo_turno_devuelve_ultimo():
    hist = [
        {"role": "user", "content": "uno", "ts": "x"},
        {"role": "assistant", "content": "dos", "ts": "y"},
    ]
    assert memoria_mod.ultimo_turno(hist)["content"] == "dos"


def test_ultimo_turno_vacio_devuelve_none():
    assert memoria_mod.ultimo_turno([]) is None


# ---------------------------------------------------------------------------
# segundos_desde_ultimo_clara
# ---------------------------------------------------------------------------

def test_segundos_desde_ultimo_clara_calcula_delta():
    hace = datetime.now() - timedelta(seconds=120)
    hist = [
        {"role": "user", "content": "hola", "ts": hace.isoformat(timespec="seconds")},
        {"role": "assistant", "content": "buenas", "ts": datetime.now().isoformat()},
    ]
    delta = memoria_mod.segundos_desde_ultimo_clara(hist)
    assert delta is not None
    # Margen amplio porque .now() cambia entre las dos llamadas
    assert 110 <= delta <= 200


def test_segundos_desde_ultimo_clara_sin_user_es_none():
    hist = [{"role": "assistant", "content": "monologo", "ts": datetime.now().isoformat()}]
    assert memoria_mod.segundos_desde_ultimo_clara(hist) is None


def test_segundos_desde_ultimo_clara_historial_vacio():
    assert memoria_mod.segundos_desde_ultimo_clara([]) is None


def test_segundos_desde_ultimo_clara_busca_el_mas_reciente():
    """Si hay varios mensajes de user, devuelve el delta del más reciente."""
    viejo = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
    reciente = (datetime.now() - timedelta(seconds=30)).isoformat(timespec="seconds")
    hist = [
        {"role": "user", "content": "viejo", "ts": viejo},
        {"role": "assistant", "content": "respuesta", "ts": viejo},
        {"role": "user", "content": "reciente", "ts": reciente},
    ]
    delta = memoria_mod.segundos_desde_ultimo_clara(hist)
    assert 25 <= delta <= 80


def test_segundos_desde_ultimo_clara_ts_invalido_devuelve_none():
    hist = [{"role": "user", "content": "hola", "ts": "no-es-fecha"}]
    assert memoria_mod.segundos_desde_ultimo_clara(hist) is None


def test_segundos_desde_ultimo_clara_sin_ts_devuelve_none():
    hist = [{"role": "user", "content": "hola"}]
    assert memoria_mod.segundos_desde_ultimo_clara(hist) is None


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_borra_archivo():
    memoria_mod.agregar_turno([], "user", "x")
    assert memoria_mod.MEMORIA_PATH.exists()
    memoria_mod.reset()
    assert not memoria_mod.MEMORIA_PATH.exists()
    assert memoria_mod.cargar_historial() == []


def test_reset_sin_archivo_no_rompe():
    assert not memoria_mod.MEMORIA_PATH.exists()
    memoria_mod.reset()  # No debe lanzar
