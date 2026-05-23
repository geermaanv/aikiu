"""Tests para andromarta/ciclo.py — ciclo de conversación abierto/cerrado."""

import json
from pathlib import Path

import pytest

from andromarta import ciclo as ciclo_mod


@pytest.fixture(autouse=True)
def _aislar_ciclo(tmp_path, monkeypatch):
    fake = tmp_path / "ciclo.json"
    monkeypatch.setattr(ciclo_mod, "CICLO_PATH", fake)
    monkeypatch.setattr(ciclo_mod, "DATA_DIR", tmp_path)
    yield


# ---------------------------------------------------------------------------
# cargar / guardar
# ---------------------------------------------------------------------------

def test_cargar_sin_archivo_crea_estado_inicial_abierto():
    estado = ciclo_mod.cargar()
    assert estado["abierto"] is True
    assert estado["turnos"] == 0
    assert "iniciado" in estado
    # Y se persistió
    assert ciclo_mod.CICLO_PATH.exists()


def test_cargar_con_estado_persistido():
    ciclo_mod.guardar({"abierto": False, "turnos": 5, "iniciado": "2026-05-22T10:00:00"})
    e = ciclo_mod.cargar()
    assert e["abierto"] is False
    assert e["turnos"] == 5


def test_cargar_con_estado_incompleto_regenera():
    """Si faltan claves obligatorias, se regenera (defensivo)."""
    ciclo_mod.CICLO_PATH.write_text(json.dumps({"abierto": True}), encoding="utf-8")  # falta turnos
    e = ciclo_mod.cargar()
    assert e["turnos"] == 0


def test_cargar_con_estado_corrupto_regenera():
    ciclo_mod.CICLO_PATH.write_text("no es json", encoding="utf-8")
    e = ciclo_mod.cargar()
    assert e["abierto"] is True
    assert e["turnos"] == 0


def test_guardar_persiste_a_disco():
    ciclo_mod.guardar({"abierto": True, "turnos": 3, "iniciado": "x"})
    en_disco = json.loads(ciclo_mod.CICLO_PATH.read_text(encoding="utf-8"))
    assert en_disco["turnos"] == 3


def test_guardar_crea_data_dir_si_no_existe(tmp_path, monkeypatch):
    nuevo_dir = tmp_path / "subdir-que-no-existe"
    nuevo_path = nuevo_dir / "ciclo.json"
    monkeypatch.setattr(ciclo_mod, "CICLO_PATH", nuevo_path)
    monkeypatch.setattr(ciclo_mod, "DATA_DIR", nuevo_dir)
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    assert nuevo_path.exists()


# ---------------------------------------------------------------------------
# esta_cerrado
# ---------------------------------------------------------------------------

def test_esta_cerrado_abierto_es_false():
    assert ciclo_mod.esta_cerrado({"abierto": True, "turnos": 0, "iniciado": "x"}) is False


def test_esta_cerrado_cerrado_es_true():
    assert ciclo_mod.esta_cerrado({"abierto": False, "turnos": 5, "iniciado": "x"}) is True


def test_esta_cerrado_sin_arg_lee_disco():
    ciclo_mod.guardar({"abierto": False, "turnos": 5, "iniciado": "x"})
    assert ciclo_mod.esta_cerrado() is True


def test_esta_cerrado_default_abierto():
    """Si el dict no tiene 'abierto', se asume True por seguridad (responde)."""
    assert ciclo_mod.esta_cerrado({"turnos": 0}) is False


# ---------------------------------------------------------------------------
# abrir_nuevo
# ---------------------------------------------------------------------------

def test_abrir_nuevo_resetea_contador_y_persiste():
    ciclo_mod.guardar({"abierto": False, "turnos": 15, "iniciado": "viejo"})
    nuevo = ciclo_mod.abrir_nuevo()
    assert nuevo["abierto"] is True
    assert nuevo["turnos"] == 0
    # Y persistió
    assert json.loads(ciclo_mod.CICLO_PATH.read_text(encoding="utf-8"))["turnos"] == 0


# ---------------------------------------------------------------------------
# registrar_turno
# ---------------------------------------------------------------------------

def test_registrar_turno_suma_uno_y_persiste():
    estado = {"abierto": True, "turnos": 3, "iniciado": "x"}
    actualizado = ciclo_mod.registrar_turno(estado)
    assert actualizado["turnos"] == 4
    en_disco = json.loads(ciclo_mod.CICLO_PATH.read_text(encoding="utf-8"))
    assert en_disco["turnos"] == 4


def test_registrar_turno_sin_turnos_inicia_en_1():
    estado = {"abierto": True, "iniciado": "x"}
    actualizado = ciclo_mod.registrar_turno(estado)
    assert actualizado["turnos"] == 1


def test_registrar_turno_acumula_multiple():
    estado = ciclo_mod.cargar()
    for _ in range(5):
        estado = ciclo_mod.registrar_turno(estado)
    assert estado["turnos"] == 5


# ---------------------------------------------------------------------------
# cerrar
# ---------------------------------------------------------------------------

def test_cerrar_marca_no_abierto_y_persiste():
    estado = {"abierto": True, "turnos": 10, "iniciado": "x"}
    cerrado = ciclo_mod.cerrar(estado)
    assert cerrado["abierto"] is False
    en_disco = json.loads(ciclo_mod.CICLO_PATH.read_text(encoding="utf-8"))
    assert en_disco["abierto"] is False


# ---------------------------------------------------------------------------
# proxima_respuesta_es_despedida
# ---------------------------------------------------------------------------

def test_proxima_es_despedida_cuando_alcanza_tope():
    """Si turnos+1 == max, la próxima respuesta es despedida."""
    estado = {"abierto": True, "turnos": 14, "iniciado": "x"}
    assert ciclo_mod.proxima_respuesta_es_despedida(estado, max_turnos=15) is True


def test_proxima_es_despedida_si_pasa_el_tope():
    estado = {"abierto": True, "turnos": 20, "iniciado": "x"}
    assert ciclo_mod.proxima_respuesta_es_despedida(estado, max_turnos=15) is True


def test_proxima_no_es_despedida_si_falta_mucho():
    estado = {"abierto": True, "turnos": 3, "iniciado": "x"}
    assert ciclo_mod.proxima_respuesta_es_despedida(estado, max_turnos=15) is False


def test_proxima_es_despedida_default_turnos_0():
    estado = {"abierto": True, "iniciado": "x"}
    assert ciclo_mod.proxima_respuesta_es_despedida(estado, max_turnos=2) is False
    estado["turnos"] = 1
    assert ciclo_mod.proxima_respuesta_es_despedida(estado, max_turnos=2) is True
