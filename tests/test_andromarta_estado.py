"""Tests para andromarta/estado.py — estado interno (ánimo, energía, eventos)."""

import json
import random
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from andromarta import estado as estado_mod


@pytest.fixture(autouse=True)
def _aislar_estado(tmp_path, monkeypatch):
    fake = tmp_path / "estado.json"
    monkeypatch.setattr(estado_mod, "ESTADO_PATH", fake)
    monkeypatch.setattr(estado_mod, "DATA_DIR", tmp_path)
    yield


# ---------------------------------------------------------------------------
# cargar_estado
# ---------------------------------------------------------------------------

def test_cargar_estado_inicial_genera_y_persiste():
    est = estado_mod.cargar_estado()
    assert est["fecha"] == date.today().isoformat()
    assert 2 <= est["animo"] <= 10
    assert 2 <= est["energia"] <= 10
    assert isinstance(est["sintomas"], list)
    assert isinstance(est["eventos"], list)
    # Y queda en disco
    assert estado_mod.ESTADO_PATH.exists()


def test_cargar_estado_mismo_dia_no_regenera():
    primero = estado_mod.cargar_estado()
    segundo = estado_mod.cargar_estado()
    # Mismo objeto persistido (fecha igual + valores iguales)
    assert primero["fecha"] == segundo["fecha"]
    assert primero["animo"] == segundo["animo"]


def test_cargar_estado_dia_anterior_regenera():
    """Si la fecha es de ayer, debe regenerar para el día actual."""
    ayer = (date.today() - timedelta(days=1)).isoformat()
    estado_viejo = {
        "fecha": ayer,
        "animo": 6,
        "energia": 6,
        "sintomas": [],
        "eventos": [],
        "ultima_actualizacion": "2026-05-21T10:00:00",
    }
    estado_mod.ESTADO_PATH.write_text(json.dumps(estado_viejo), encoding="utf-8")
    nuevo = estado_mod.cargar_estado()
    assert nuevo["fecha"] == date.today().isoformat()
    # Continuidad: el nuevo está cerca del viejo (±2)
    assert abs(nuevo["animo"] - 6) <= 2
    assert abs(nuevo["energia"] - 6) <= 2


def test_cargar_estado_clampa_animo_a_rango_valido():
    """Aunque el random salte fuera del rango, animo siempre queda entre 2 y 10."""
    ayer = (date.today() - timedelta(days=1)).isoformat()
    estado_viejo = {"fecha": ayer, "animo": 10, "energia": 2, "sintomas": [], "eventos": []}
    estado_mod.ESTADO_PATH.write_text(json.dumps(estado_viejo), encoding="utf-8")
    nuevo = estado_mod.cargar_estado()
    assert 2 <= nuevo["animo"] <= 10
    assert 2 <= nuevo["energia"] <= 10


# ---------------------------------------------------------------------------
# guardar_estado
# ---------------------------------------------------------------------------

def test_guardar_estado_actualiza_timestamp():
    est = {"fecha": "2026-05-22", "animo": 8, "energia": 7, "sintomas": [], "eventos": []}
    estado_mod.guardar_estado(est)
    en_disco = json.loads(estado_mod.ESTADO_PATH.read_text(encoding="utf-8"))
    assert en_disco["animo"] == 8
    assert "ultima_actualizacion" in en_disco


# ---------------------------------------------------------------------------
# descripcion_humana
# ---------------------------------------------------------------------------

def test_descripcion_humana_animo_alto():
    desc = estado_mod.descripcion_humana({"animo": 9, "energia": 8, "sintomas": [], "eventos": []})
    assert "buen humor" in desc.lower() or "conversadora" in desc.lower()


def test_descripcion_humana_animo_medio():
    desc = estado_mod.descripcion_humana({"animo": 6, "energia": 6, "sintomas": [], "eventos": []})
    assert "tranquilo" in desc.lower() or "ni feliz" in desc.lower()


def test_descripcion_humana_animo_bajo():
    desc = estado_mod.descripcion_humana({"animo": 3, "energia": 5, "sintomas": [], "eventos": []})
    assert "melancólica" in desc.lower() or "poca chispa" in desc.lower()


def test_descripcion_humana_energia_baja_se_menciona():
    desc = estado_mod.descripcion_humana({"animo": 6, "energia": 3, "sintomas": [], "eventos": []})
    assert "poca energía" in desc.lower() or "lenta" in desc.lower()


def test_descripcion_humana_incluye_sintomas():
    desc = estado_mod.descripcion_humana({
        "animo": 6, "energia": 6,
        "sintomas": ["rodillas", "no dormí bien"],
        "eventos": [],
    })
    assert "rodillas" in desc
    assert "no dormí bien" in desc


def test_descripcion_humana_incluye_eventos():
    desc = estado_mod.descripcion_humana({
        "animo": 6, "energia": 6, "sintomas": [],
        "eventos": ["llamó mi hijo Roberto"],
    })
    assert "Roberto" in desc


def test_descripcion_humana_sin_sintomas_ni_eventos():
    desc = estado_mod.descripcion_humana({"animo": 6, "energia": 6, "sintomas": [], "eventos": []})
    assert isinstance(desc, str) and len(desc) > 0
    assert "Síntoma" not in desc
    assert "Evento" not in desc


def test_descripcion_humana_estado_vacio_usa_defaults():
    """Si faltan keys, no debe romper — usa 6/6 por default."""
    desc = estado_mod.descripcion_humana({})
    assert isinstance(desc, str) and len(desc) > 0


# ---------------------------------------------------------------------------
# hora_del_dia
# ---------------------------------------------------------------------------

def _patch_hora(hour: int):
    """Patchea datetime.now() en el módulo para devolver una hora dada."""
    from datetime import datetime as real_dt
    class _FakeDT:
        @staticmethod
        def now():
            return real_dt(2026, 5, 22, hour, 0, 0)
    return patch.object(estado_mod, "datetime", _FakeDT)


def test_hora_del_dia_manana():
    with _patch_hora(8):
        assert estado_mod.hora_del_dia() == "mañana"


def test_hora_del_dia_mediodia():
    with _patch_hora(12):
        assert estado_mod.hora_del_dia() == "mediodía"


def test_hora_del_dia_tarde():
    with _patch_hora(15):
        assert estado_mod.hora_del_dia() == "tarde"


def test_hora_del_dia_noche():
    with _patch_hora(20):
        assert estado_mod.hora_del_dia() == "noche"


def test_hora_del_dia_madrugada():
    with _patch_hora(3):
        assert estado_mod.hora_del_dia() == "madrugada"


def test_hora_del_dia_limites():
    # 6 entra en mañana; 11 entra en mediodía; 14 entra en tarde; 18 entra en noche; 22 entra en madrugada
    with _patch_hora(6):
        assert estado_mod.hora_del_dia() == "mañana"
    with _patch_hora(11):
        assert estado_mod.hora_del_dia() == "mediodía"
    with _patch_hora(14):
        assert estado_mod.hora_del_dia() == "tarde"
    with _patch_hora(18):
        assert estado_mod.hora_del_dia() == "noche"
    with _patch_hora(22):
        assert estado_mod.hora_del_dia() == "madrugada"


# ---------------------------------------------------------------------------
# probabilidad_iniciativa
# ---------------------------------------------------------------------------

def test_probabilidad_iniciativa_segun_franja():
    with _patch_hora(8):
        assert estado_mod.probabilidad_iniciativa() == 0.35  # mañana
    with _patch_hora(12):
        assert estado_mod.probabilidad_iniciativa() == 0.15  # mediodía
    with _patch_hora(15):
        assert estado_mod.probabilidad_iniciativa() == 0.25  # tarde
    with _patch_hora(20):
        assert estado_mod.probabilidad_iniciativa() == 0.20  # noche
    with _patch_hora(3):
        assert estado_mod.probabilidad_iniciativa() == 0.02  # madrugada


# ---------------------------------------------------------------------------
# _nuevo_dia (vía cargar_estado)
# ---------------------------------------------------------------------------

def test_nuevo_dia_sin_ayer_usa_base_6():
    """Si no hay estado de ayer, usa base 6 (visible vía cargar_estado)."""
    with patch.object(random, "randint", return_value=0), \
         patch.object(random, "random", return_value=1.0), \
         patch.object(random, "choices", return_value=[0]):
        est = estado_mod.cargar_estado()
    assert est["animo"] == 6
    assert est["energia"] == 6
    assert est["sintomas"] == []
    assert est["eventos"] == []


def test_nuevo_dia_con_eventos_no_duplica():
    """Si la rifa elige el mismo evento dos veces, no se duplica."""
    # Forzamos 2 eventos pero el mismo siempre
    with patch.object(random, "randint", return_value=0), \
         patch.object(random, "random", return_value=1.0), \
         patch.object(random, "choice", return_value="llamó mi hijo Roberto"), \
         patch.object(random, "choices", return_value=[2]):
        est = estado_mod.cargar_estado()
    assert est["eventos"] == ["llamó mi hijo Roberto"]
