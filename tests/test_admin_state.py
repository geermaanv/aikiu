"""Tests para core/admin_state.py — TOFU del admin_chat_id."""

import json
import pytest

from core import admin_state


@pytest.fixture(autouse=True)
def _aislar_admin_state(tmp_path, monkeypatch):
    state_file = tmp_path / "admin_state.json"
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", state_file)
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    yield


def test_sin_admin_es_none():
    assert admin_state.admin_chat_id() is None
    assert admin_state.tiene_admin() is False
    assert admin_state.es_admin(123) is False


def test_registrar_primera_vez():
    assert admin_state.registrar_admin(42) is True
    assert admin_state.admin_chat_id() == 42
    assert admin_state.tiene_admin() is True
    assert admin_state.es_admin(42) is True
    assert admin_state.es_admin(99) is False


def test_registrar_segunda_vez_no_sobreescribe():
    admin_state.registrar_admin(42)
    assert admin_state.registrar_admin(99) is False
    assert admin_state.admin_chat_id() == 42
    assert admin_state.es_admin(42) is True


def test_persiste_en_disco():
    admin_state.registrar_admin(7)
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    assert data["admin_chat_id"] == 7
    assert "registered_at" in data


def test_registrar_guarda_int_no_str():
    admin_state.registrar_admin("123456")
    data = json.loads(admin_state.ADMIN_STATE_PATH.read_text(encoding="utf-8"))
    assert data["admin_chat_id"] == 123456
    assert isinstance(data["admin_chat_id"], int)


def test_env_override_tiene_prioridad(monkeypatch):
    admin_state.registrar_admin(111)
    monkeypatch.setenv("ADMIN_CHAT_ID", "999")
    assert admin_state.admin_chat_id() == 999
    assert admin_state.es_admin(999) is True
    assert admin_state.es_admin(111) is False


def test_env_placeholder_ignorado(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "PEGA_TU_ADMIN_CHAT_ID")
    assert admin_state.admin_chat_id() is None
    admin_state.registrar_admin(55)
    assert admin_state.admin_chat_id() == 55


def test_env_invalido_ignorado(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "no-es-numero")
    assert admin_state.admin_chat_id() is None


def test_env_bloquea_registro(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "777")
    assert admin_state.registrar_admin(123) is False
    assert not admin_state.ADMIN_STATE_PATH.exists()


def test_reset_borra_persistido():
    admin_state.registrar_admin(42)
    assert admin_state.reset_admin() is True
    assert admin_state.admin_chat_id() is None


def test_reset_sin_admin_es_noop():
    assert admin_state.reset_admin() is False


def test_reset_permite_re_registro():
    admin_state.registrar_admin(1)
    admin_state.reset_admin()
    assert admin_state.registrar_admin(2) is True
    assert admin_state.admin_chat_id() == 2


def test_corrupto_se_trata_como_vacio():
    admin_state.ADMIN_STATE_PATH.write_text("{ no es json", encoding="utf-8")
    assert admin_state.admin_chat_id() is None
    assert admin_state.registrar_admin(10) is True
    assert admin_state.admin_chat_id() == 10


def test_es_admin_acepta_str_e_int():
    admin_state.registrar_admin(42)
    assert admin_state.es_admin(42) is True
    assert admin_state.es_admin("42") is True
