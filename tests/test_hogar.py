"""
Tests para core/hogar.py — modelo de hogares (instances) multi-tenant.

Cada test aísla AIKIU_REGISTRY a un directorio temporal para no tocar
`instances/` real del repo.
"""

import json

import pytest

from core import hogar as hogar_mod


@pytest.fixture(autouse=True)
def _aislar_registry(tmp_path, monkeypatch):
    """Apunta `AIKIU_REGISTRY` a un tmpdir limpio en cada test."""
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    yield


# ---------------------------------------------------------------------------
# Localización
# ---------------------------------------------------------------------------

def test_instances_root_lee_env(tmp_path):
    assert hogar_mod.instances_root() == tmp_path


def test_instances_root_default_sin_env(monkeypatch, tmp_path):
    monkeypatch.delenv("AIKIU_REGISTRY", raising=False)
    # Sin env → BASE_DIR/instances/
    assert hogar_mod.instances_root() == hogar_mod.BASE_DIR / "instances"


def test_hogar_dir_es_subdir_por_chat_id(tmp_path):
    assert hogar_mod.hogar_dir(42) == tmp_path / "42"
    assert hogar_mod.hogar_dir("99") == tmp_path / "99"


# ---------------------------------------------------------------------------
# CRUD básico
# ---------------------------------------------------------------------------

def test_crear_hogar_idempotente(tmp_path):
    d1 = hogar_mod.crear_hogar(123)
    d2 = hogar_mod.crear_hogar(123)
    assert d1 == d2 == tmp_path / "123"
    assert (d1 / "state.json").exists()


def test_crear_hogar_guarda_chat_id_y_fecha(tmp_path):
    hogar_mod.crear_hogar(456, nombre="Lola")
    data = json.loads((tmp_path / "456" / "state.json").read_text(encoding="utf-8"))
    assert data["owner_chat_id"] == 456
    assert data["nombre_adulto"] == "Lola"
    assert "registered_at" in data


def test_existe_hogar_false_si_no_creado():
    assert hogar_mod.existe_hogar(789) is False


def test_existe_hogar_true_post_create():
    hogar_mod.crear_hogar(789)
    assert hogar_mod.existe_hogar(789) is True
    assert hogar_mod.existe_hogar("789") is True


def test_existe_hogar_false_sin_state_json(tmp_path):
    """Un directorio suelto sin state.json no cuenta como hogar."""
    (tmp_path / "555").mkdir()
    assert hogar_mod.existe_hogar(555) is False


def test_listar_hogares_vacio_devuelve_lista_vacia():
    assert hogar_mod.listar_hogares() == []


def test_listar_hogares_devuelve_ids_ordenados():
    for cid in [333, 111, 222]:
        hogar_mod.crear_hogar(cid)
    assert hogar_mod.listar_hogares() == [111, 222, 333]


def test_listar_hogares_ignora_subdirs_invalidos(tmp_path):
    hogar_mod.crear_hogar(100)
    # Subdir con nombre no numérico
    (tmp_path / "no-es-un-chat-id").mkdir()
    # Subdir numérico pero sin state.json
    (tmp_path / "999").mkdir()
    assert hogar_mod.listar_hogares() == [100]


def test_borrar_hogar_devuelve_true_si_existia():
    hogar_mod.crear_hogar(42)
    assert hogar_mod.borrar_hogar(42) is True
    assert hogar_mod.existe_hogar(42) is False


def test_borrar_hogar_inexistente_devuelve_false():
    assert hogar_mod.borrar_hogar(9999) is False


# ---------------------------------------------------------------------------
# Paths derivados por hogar
# ---------------------------------------------------------------------------

def test_paths_apuntan_dentro_del_hogar(tmp_path):
    d = tmp_path / "42"
    assert hogar_mod.state_path(42) == d / "state.json"
    assert hogar_mod.perfil_path(42) == d / "perfil.md"
    assert hogar_mod.stats_path(42) == d / "stats.json"
    assert hogar_mod.receptividad_path(42) == d / "receptividad.json"
    assert hogar_mod.familiares_path(42) == d / "familiares.json"
    assert hogar_mod.logs_dir(42) == d / "logs"
    assert hogar_mod.config_path(42) == d / "config.yml"


# ---------------------------------------------------------------------------
# Lectura/escritura del state
# ---------------------------------------------------------------------------

def test_leer_state_inexistente_devuelve_vacio():
    assert hogar_mod.leer_state(123) == {}


def test_escribir_y_leer_state_roundtrip():
    hogar_mod.crear_hogar(42)
    hogar_mod.escribir_state(42, {"owner_chat_id": 42, "extra": "valor"})
    assert hogar_mod.leer_state(42) == {"owner_chat_id": 42, "extra": "valor"}


def test_actualizar_state_mergea(tmp_path):
    hogar_mod.crear_hogar(42)
    hogar_mod.actualizar_state(42, ciudad="Olivos", voz="es-AR-ElenaNeural")
    estado = hogar_mod.leer_state(42)
    assert estado["owner_chat_id"] == 42
    assert estado["ciudad"] == "Olivos"
    assert estado["voz"] == "es-AR-ElenaNeural"


def test_escritura_atomica_no_deja_tmp(tmp_path):
    hogar_mod.crear_hogar(42)
    hogar_mod.escribir_state(42, {"x": 1})
    # No deben quedar archivos .state.json.*.tmp huérfanos.
    tmps = list((tmp_path / "42").glob(".*.tmp"))
    assert tmps == []


def test_state_corrupto_se_trata_como_vacio(tmp_path):
    d = tmp_path / "42"
    d.mkdir()
    (d / "state.json").write_text("{ esto no es json", encoding="utf-8")
    assert hogar_mod.leer_state(42) == {}
