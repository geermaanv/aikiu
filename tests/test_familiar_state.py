"""Tests para core/familiar_state.py — estado del familiar y many-to-many."""

import pytest

from core import familiar_state as fs
from core import hogar as hogar_mod


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    yield


def test_asegurar_familiar_nuevo_devuelve_true():
    assert fs.asegurar_familiar(101, nombre="Germán") is True
    estado = fs.leer_estado(101)
    assert estado["nombre"] == "Germán"
    assert estado["adulto_activo"] is None


def test_asegurar_familiar_existente_devuelve_false():
    fs.asegurar_familiar(101, nombre="Germán")
    assert fs.asegurar_familiar(101) is False


def test_asegurar_familiar_completa_nombre_si_faltaba():
    fs.asegurar_familiar(101)  # sin nombre
    fs.asegurar_familiar(101, nombre="Germán")
    assert fs.leer_estado(101)["nombre"] == "Germán"


def test_actualizar_nombre_cambia_el_nombre():
    fs.asegurar_familiar(101, nombre="Germán")
    fs.actualizar_nombre(101, "Lao")
    assert fs.leer_estado(101)["nombre"] == "Lao"


def test_actualizar_nombre_da_de_alta_si_no_existia():
    fs.actualizar_nombre(101, "Lao")
    assert fs.leer_estado(101)["nombre"] == "Lao"


def test_nombre_de_con_fallback():
    assert fs.nombre_de(999, fallback="X") == "X"
    fs.asegurar_familiar(999, nombre="Ana")
    assert fs.nombre_de(999) == "Ana"


def test_adultos_de_familiar_sin_vinculos():
    assert fs.adultos_de(101) == []


def test_vincular_un_solo_adulto_y_es_activo_automaticamente():
    hogar_mod.crear_hogar(42)
    fs.asegurar_familiar(101, nombre="Germán")
    assert fs.vincular(101, 42, nombre="Germán") is True
    assert fs.adultos_de(101) == [42]
    assert fs.adulto_activo(101) == 42


def test_vincular_dos_veces_es_idempotente():
    hogar_mod.crear_hogar(42)
    fs.vincular(101, 42, nombre="Germán")
    assert fs.vincular(101, 42, nombre="Germán") is False
    assert fs.adultos_de(101) == [42]


def test_vincular_a_hogar_inexistente_devuelve_false():
    assert fs.vincular(101, 999) is False


def test_vincular_dos_adultos_y_adulto_activo_se_mantiene_en_el_primero():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42, nombre="Germán")
    fs.vincular(101, 99, nombre="Germán")
    vinculados = sorted(fs.adultos_de(101))
    assert vinculados == [42, 99]
    # El activo sigue siendo el primero (42), no se mueve solo
    assert fs.adulto_activo(101) == 42


def test_adulto_activo_con_dos_y_sin_eleccion_devuelve_none():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42)
    fs.setear_adulto_activo(101, None)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, None)
    assert fs.adulto_activo(101) is None


def test_setear_adulto_activo_cambia_el_default():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, 99)
    assert fs.adulto_activo(101) == 99


def test_desvincular_quita_al_familiar():
    hogar_mod.crear_hogar(42)
    fs.vincular(101, 42)
    assert fs.desvincular(101, 42) is True
    assert fs.adultos_de(101) == []


def test_desvincular_ajusta_el_activo_si_era_el_borrado():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, 42)
    fs.desvincular(101, 42)
    # Como queda solo 99, activo pasa a ser 99
    assert fs.adulto_activo(101) == 99


def test_desvincular_si_no_estaba_devuelve_false():
    hogar_mod.crear_hogar(42)
    assert fs.desvincular(101, 42) is False


# ---------------------------------------------------------------------------
# limpiar_hogar_borrado: reasigna el adulto_activo huérfano
# ---------------------------------------------------------------------------

def test_limpiar_hogar_borrado_reasigna_activo_a_otro_vinculo():
    """Familiar tenía dos adultos vinculados con uno activo. Si se borra
    el hogar del activo, el activo se reasigna al otro vínculo sin
    intervención del familiar."""
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, 42)
    # Admin borra el hogar 42 (simulamos solo el rmtree, no la limpieza completa)
    hogar_mod.borrar_hogar(42)
    afectados = fs.limpiar_hogar_borrado(42)
    assert afectados == 1
    # Después del borrado, el activo es el único que queda
    assert fs.adulto_activo(101) == 99


def test_limpiar_hogar_borrado_deja_activo_none_si_no_quedan_vinculos():
    hogar_mod.crear_hogar(42)
    fs.vincular(101, 42)
    fs.setear_adulto_activo(101, 42)
    hogar_mod.borrar_hogar(42)
    fs.limpiar_hogar_borrado(42)
    assert fs.adulto_activo(101) is None
    # El estado conservó al familiar pero con activo=None
    assert fs.leer_estado(101).get("adulto_activo") is None


def test_limpiar_hogar_borrado_no_toca_a_familiares_que_no_tenian_ese_activo():
    """Familiares vinculados a OTRO hogar no se ven afectados al borrar
    un hogar que no era el suyo."""
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    fs.vincular(101, 42)   # 101 → activo=42 (auto, único vínculo)
    fs.vincular(202, 99)   # 202 → activo=99 (auto, único vínculo)
    hogar_mod.borrar_hogar(42)
    fs.limpiar_hogar_borrado(42)
    # 101 perdió su único vínculo: activo None
    assert fs.adulto_activo(101) is None
    # 202 sigue intacto operando sobre 99
    assert fs.adulto_activo(202) == 99
    assert fs.leer_estado(202).get("adulto_activo") == 99
