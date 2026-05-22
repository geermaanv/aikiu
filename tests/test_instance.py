"""Tests para core/instance.py — abstracción multi-tenant."""

import pytest

from core import instance as inst_mod


@pytest.fixture(autouse=True)
def _aislar_env(monkeypatch):
    monkeypatch.delenv("AIKIU_INSTANCE_ID", raising=False)
    monkeypatch.delenv("AIKIU_REGISTRY", raising=False)
    yield


def test_instance_id_default():
    assert inst_mod.instance_id() == "default"


def test_instance_id_desde_env(monkeypatch):
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "marta-bsas")
    assert inst_mod.instance_id() == "marta-bsas"


def test_instance_id_vacio_cae_a_default(monkeypatch):
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "   ")
    assert inst_mod.instance_id() == "default"


def test_instance_dir_sin_registry_es_base_dir():
    assert inst_mod.instance_dir() == inst_mod.BASE_DIR


def test_instance_dir_con_registry_arma_subdir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "marta")
    d = inst_mod.instance_dir()
    assert d == tmp_path / "marta"
    assert d.exists() and d.is_dir()


def test_descubrir_instancias_sin_registry_devuelve_solo_base():
    assert inst_mod.descubrir_instancias() == [inst_mod.BASE_DIR]


def test_descubrir_instancias_con_registry_lista_subdirs(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    # Sin contenido en registry → fallback a [instance_dir()]
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "default")
    instancias = inst_mod.descubrir_instancias()
    # No hay subdirs con heartbeat; debe devolver el dir actual de instancia (creado)
    assert len(instancias) == 1

    # Creamos dos instancias con heartbeats
    (tmp_path / "marta").mkdir()
    (tmp_path / "marta" / "heartbeat-aikiu.json").write_text("{}", encoding="utf-8")
    (tmp_path / "juan").mkdir()
    (tmp_path / "juan" / "heartbeat-aikiu.json").write_text("{}", encoding="utf-8")
    (tmp_path / "no_instancia").mkdir()  # sin heartbeat → no debe contar

    instancias = inst_mod.descubrir_instancias()
    nombres = {p.name for p in instancias}
    assert "marta" in nombres and "juan" in nombres
    assert "no_instancia" not in nombres


def test_descubrir_acepta_config_yml_como_marcador(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path))
    (tmp_path / "pepe").mkdir()
    (tmp_path / "pepe" / "config.yml").write_text("nombre_adulto_mayor: Pepe", encoding="utf-8")
    instancias = inst_mod.descubrir_instancias()
    assert tmp_path / "pepe" in instancias


def test_nombre_adulto_de_lee_config_yml(tmp_path):
    (tmp_path / "config.yml").write_text(
        "nombre_adulto_mayor: \"Marta\"\n", encoding="utf-8"
    )
    assert inst_mod.nombre_adulto_de(tmp_path) == "Marta"


def test_nombre_adulto_de_fallback_a_dirname(tmp_path):
    assert inst_mod.nombre_adulto_de(tmp_path) == tmp_path.name


def test_id_de_base_dir_devuelve_instance_id_actual(monkeypatch):
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "marta")
    assert inst_mod.id_de(inst_mod.BASE_DIR) == "marta"


def test_id_de_subdir_devuelve_dirname(tmp_path):
    sub = tmp_path / "juan"
    sub.mkdir()
    assert inst_mod.id_de(sub) == "juan"
