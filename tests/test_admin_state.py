"""Tests para admin/state.py — multi-admin con cupo abierto."""

import json
import pytest

from admin import state as admin_state


@pytest.fixture(autouse=True)
def _aislar_admin_state(tmp_path, monkeypatch):
    state_file = tmp_path / "admin_state.json"
    legacy_file = tmp_path / "legacy_admin_state.json"
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", state_file)
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", legacy_file)
    # Limpieza de overrides para que cada test parta de cero
    for env_var in ("ADMIN_CHAT_ID", "ADMIN_CHAT_IDS", "ADMIN_MAX_USERS"):
        monkeypatch.delenv(env_var, raising=False)
    yield


# ---------------------------------------------------------------------------
# Estado inicial
# ---------------------------------------------------------------------------

def test_sin_admin_es_lista_vacia():
    assert admin_state.admin_chat_ids() == []
    assert admin_state.admin_chat_id() is None
    assert admin_state.tiene_admin() is False
    assert admin_state.admin_count() == 0
    assert admin_state.hay_cupo() is True
    assert admin_state.es_admin(123) is False


def test_default_cupo_es_5():
    assert admin_state.admins_max() == 5


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def test_registrar_primera_vez():
    assert admin_state.registrar_admin(42) is True
    assert admin_state.admin_chat_ids() == [42]
    assert admin_state.admin_chat_id() == 42
    assert admin_state.tiene_admin() is True
    assert admin_state.admin_count() == 1
    assert admin_state.es_admin(42) is True
    assert admin_state.es_admin(99) is False


def test_registrar_segunda_vez_suma_admin_si_hay_cupo():
    """Cambio respecto al modelo single-admin viejo: ahora el segundo /start
    suma un admin más en vez de fallar."""
    admin_state.registrar_admin(42)
    assert admin_state.registrar_admin(99) is True
    assert admin_state.admin_chat_ids() == [42, 99]
    assert admin_state.admin_count() == 2
    assert admin_state.es_admin(42) is True
    assert admin_state.es_admin(99) is True


def test_registrar_duplicado_no_dupica():
    admin_state.registrar_admin(42)
    assert admin_state.registrar_admin(42) is False
    assert admin_state.admin_chat_ids() == [42]


def test_registrar_cupo_lleno_rechaza():
    for cid in (10, 20, 30, 40, 50):
        assert admin_state.registrar_admin(cid) is True
    assert admin_state.admin_count() == 5
    assert admin_state.hay_cupo() is False
    assert admin_state.registrar_admin(60) is False
    assert admin_state.admin_count() == 5


def test_registrar_respeta_admin_max_users(monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_USERS", "2")
    assert admin_state.admins_max() == 2
    assert admin_state.registrar_admin(1) is True
    assert admin_state.registrar_admin(2) is True
    assert admin_state.registrar_admin(3) is False
    assert admin_state.admin_chat_ids() == [1, 2]


def test_admin_max_invalido_cae_al_default(monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_USERS", "no-es-numero")
    assert admin_state.admins_max() == admin_state.DEFAULT_ADMIN_MAX_USERS
    monkeypatch.setenv("ADMIN_MAX_USERS", "0")
    assert admin_state.admins_max() == admin_state.DEFAULT_ADMIN_MAX_USERS


def test_persiste_en_disco():
    admin_state.registrar_admin(7)
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert len(data["admins"]) == 1
    assert data["admins"][0]["chat_id"] == 7
    assert "registered_at" in data["admins"][0]


def test_registrar_acepta_string_pero_persiste_int():
    admin_state.registrar_admin("123456")
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    assert data["admins"][0]["chat_id"] == 123456
    assert isinstance(data["admins"][0]["chat_id"], int)


def test_registrar_con_added_by_persiste_auditoria():
    admin_state.registrar_admin(1)
    admin_state.registrar_admin(2, added_by=1)
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    # admins[0] no tiene added_by, admins[1] sí
    assert "added_by" not in data["admins"][0]
    assert data["admins"][1]["added_by"] == 1


# ---------------------------------------------------------------------------
# Quitar
# ---------------------------------------------------------------------------

def test_quitar_admin_existente():
    admin_state.registrar_admin(1)
    admin_state.registrar_admin(2)
    assert admin_state.quitar_admin(1) is True
    assert admin_state.admin_chat_ids() == [2]
    assert admin_state.es_admin(1) is False


def test_quitar_admin_inexistente_es_noop():
    admin_state.registrar_admin(1)
    assert admin_state.quitar_admin(999) is False
    assert admin_state.admin_chat_ids() == [1]


def test_quitar_libera_cupo():
    for cid in range(1, 6):
        admin_state.registrar_admin(cid)
    assert admin_state.hay_cupo() is False
    admin_state.quitar_admin(3)
    assert admin_state.hay_cupo() is True
    assert admin_state.registrar_admin(100) is True
    assert admin_state.admin_count() == 5


def test_reset_borra_todos():
    admin_state.registrar_admin(1)
    admin_state.registrar_admin(2)
    admin_state.registrar_admin(3)
    assert admin_state.reset_admin() is True
    assert admin_state.admin_chat_ids() == []
    assert admin_state.tiene_admin() is False


def test_reset_sin_admin_es_noop():
    assert admin_state.reset_admin() is False


def test_reset_permite_re_registro():
    admin_state.registrar_admin(1)
    admin_state.reset_admin()
    assert admin_state.registrar_admin(2) is True
    assert admin_state.admin_chat_ids() == [2]


# ---------------------------------------------------------------------------
# Env override
# ---------------------------------------------------------------------------

def test_env_chat_ids_lista_tiene_prioridad(monkeypatch):
    admin_state.registrar_admin(111)
    monkeypatch.setenv("ADMIN_CHAT_IDS", "999, 888, 777")
    assert admin_state.admin_chat_ids() == [999, 888, 777]
    assert admin_state.es_admin(999) is True
    assert admin_state.es_admin(888) is True
    assert admin_state.es_admin(111) is False


def test_env_chat_id_singular_es_retrocompat(monkeypatch):
    """El viejo ADMIN_CHAT_ID singular sigue funcionando."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "555")
    assert admin_state.admin_chat_ids() == [555]
    assert admin_state.es_admin(555) is True


def test_env_chat_ids_dedupea(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "111, 222, 111, 333, 222")
    assert admin_state.admin_chat_ids() == [111, 222, 333]


def test_env_chat_ids_ignora_invalidos(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "111, no-num, 222, , 333")
    assert admin_state.admin_chat_ids() == [111, 222, 333]


def test_env_placeholder_ignorado(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "PEGA_TU_ADMIN_CHAT_IDS")
    assert admin_state.admin_chat_ids() == []
    admin_state.registrar_admin(55)
    assert admin_state.admin_chat_ids() == [55]


def test_env_bloquea_registro_y_quitar(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "777, 888")
    assert admin_state.registrar_admin(123) is False
    assert admin_state.quitar_admin(777) is False
    assert not admin_state.ADMIN_STATE_PATH.exists()
    assert admin_state.admin_chat_ids() == [777, 888]


# ---------------------------------------------------------------------------
# Migración del formato viejo (single admin → lista)
# ---------------------------------------------------------------------------

def test_lee_formato_viejo_single_admin():
    admin_state.ADMIN_STATE_PATH.write_text(
        json.dumps({"admin_chat_id": 314, "registered_at": "2025-01-01T00:00:00"}),
        encoding="utf-8",
    )
    assert admin_state.admin_chat_ids() == [314]
    assert admin_state.admin_chat_id() == 314
    assert admin_state.es_admin(314) is True


def test_formato_viejo_se_reescribe_al_modificar():
    admin_state.ADMIN_STATE_PATH.write_text(
        json.dumps({"admin_chat_id": 314, "registered_at": "2025-01-01T00:00:00"}),
        encoding="utf-8",
    )
    admin_state.registrar_admin(900)
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert [a["chat_id"] for a in data["admins"]] == [314, 900]


def test_migra_legacy_path_a_admin_dir():
    """Si existe el JSON en la raíz del repo (legacy) y todavía no hay en
    admin/, se migra al primer read."""
    admin_state.LEGACY_ADMIN_STATE_PATH.write_text(
        json.dumps({"admin_chat_id": 314, "registered_at": "2025-01-01T00:00:00"}),
        encoding="utf-8",
    )
    assert not admin_state.ADMIN_STATE_PATH.exists()
    assert admin_state.admin_chat_ids() == [314]
    assert admin_state.ADMIN_STATE_PATH.exists()
    assert not admin_state.LEGACY_ADMIN_STATE_PATH.exists()


def test_corrupto_se_trata_como_vacio():
    admin_state.ADMIN_STATE_PATH.write_text("{ no es json", encoding="utf-8")
    assert admin_state.admin_chat_ids() == []
    assert admin_state.registrar_admin(10) is True
    assert admin_state.admin_chat_ids() == [10]


# ---------------------------------------------------------------------------
# listar_admins (metadata)
# ---------------------------------------------------------------------------

def test_listar_admins_incluye_registered_at():
    admin_state.registrar_admin(7)
    lista = admin_state.listar_admins()
    assert len(lista) == 1
    assert lista[0]["chat_id"] == 7
    assert "registered_at" in lista[0]


def test_listar_admins_marca_source_env(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "100, 200")
    lista = admin_state.listar_admins()
    assert lista == [
        {"chat_id": 100, "source": "env"},
        {"chat_id": 200, "source": "env"},
    ]


def test_es_admin_acepta_str_e_int():
    admin_state.registrar_admin(42)
    assert admin_state.es_admin(42) is True
    assert admin_state.es_admin("42") is True
