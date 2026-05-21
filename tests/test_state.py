"""
Tests para core/state.py — TOFU del owner_chat_id.

Cada test usa monkeypatch para apuntar STATE_PATH a un archivo temporal,
así no toca el state.json real del repo. Lo mismo para la env CHAT_ID
(override de compat).
"""

import json
import os
import pytest

from core import state as state_mod


@pytest.fixture(autouse=True)
def _aislar_state(tmp_path, monkeypatch):
    """Aísla STATE_PATH y limpia CHAT_ID del entorno para cada test."""
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(state_mod, "STATE_PATH", state_file)
    monkeypatch.delenv("CHAT_ID", raising=False)
    yield


# ---------------------------------------------------------------------------
# Estado inicial
# ---------------------------------------------------------------------------

def test_owner_chat_id_sin_state_es_none():
    assert state_mod.owner_chat_id() is None
    assert state_mod.tiene_owner() is False


def test_es_owner_sin_state_siempre_false():
    assert state_mod.es_owner(123) is False
    assert state_mod.es_owner(0) is False


# ---------------------------------------------------------------------------
# Registro TOFU
# ---------------------------------------------------------------------------

def test_registrar_owner_primera_vez():
    assert state_mod.registrar_owner(42) is True
    assert state_mod.owner_chat_id() == 42
    assert state_mod.tiene_owner() is True
    assert state_mod.es_owner(42) is True


def test_registrar_owner_segunda_vez_no_sobreescribe():
    state_mod.registrar_owner(42)
    assert state_mod.registrar_owner(99) is False
    assert state_mod.owner_chat_id() == 42
    assert state_mod.es_owner(42) is True
    assert state_mod.es_owner(99) is False


def test_registrar_owner_persiste_en_disco():
    state_mod.registrar_owner(7)
    data = json.loads(state_mod.STATE_PATH.read_text(encoding="utf-8"))
    assert data["owner_chat_id"] == 7
    assert "registered_at" in data


def test_registrar_owner_guarda_int_no_str():
    state_mod.registrar_owner("123456")  # tipo flexible — Telegram da int
    data = json.loads(state_mod.STATE_PATH.read_text(encoding="utf-8"))
    assert data["owner_chat_id"] == 123456
    assert isinstance(data["owner_chat_id"], int)


# ---------------------------------------------------------------------------
# Override por .env (compat hacia atrás)
# ---------------------------------------------------------------------------

def test_env_chat_id_tiene_prioridad(monkeypatch):
    state_mod.registrar_owner(111)
    monkeypatch.setenv("CHAT_ID", "999")
    assert state_mod.owner_chat_id() == 999
    assert state_mod.es_owner(999) is True
    assert state_mod.es_owner(111) is False


def test_env_chat_id_placeholder_ignorado(monkeypatch):
    monkeypatch.setenv("CHAT_ID", "PEGA_TU_TELEGRAM_CHAT_ID_AQUI")
    assert state_mod.owner_chat_id() is None
    state_mod.registrar_owner(55)
    assert state_mod.owner_chat_id() == 55


def test_env_chat_id_invalido_ignorado(monkeypatch):
    monkeypatch.setenv("CHAT_ID", "not-a-number")
    assert state_mod.owner_chat_id() is None


def test_env_chat_id_bloquea_registro(monkeypatch):
    """Si CHAT_ID está en .env, registrar_owner no debe escribir state.json."""
    monkeypatch.setenv("CHAT_ID", "777")
    assert state_mod.registrar_owner(123) is False
    assert not state_mod.STATE_PATH.exists()


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_owner_borra_persistido():
    state_mod.registrar_owner(42)
    assert state_mod.reset_owner() is True
    assert state_mod.owner_chat_id() is None
    assert state_mod.tiene_owner() is False


def test_reset_sin_owner_es_noop():
    assert state_mod.reset_owner() is False


def test_reset_permite_re_registro():
    state_mod.registrar_owner(1)
    state_mod.reset_owner()
    assert state_mod.registrar_owner(2) is True
    assert state_mod.owner_chat_id() == 2


# ---------------------------------------------------------------------------
# Robustez del archivo
# ---------------------------------------------------------------------------

def test_state_corrupto_se_trata_como_vacio():
    state_mod.STATE_PATH.write_text("{ esto no es json", encoding="utf-8")
    # No debe lanzar; lo trata como vacío.
    assert state_mod.owner_chat_id() is None
    # Y permite registrar arriba (sobrescribe el archivo corrupto).
    assert state_mod.registrar_owner(10) is True
    assert state_mod.owner_chat_id() == 10


def test_escritura_atomica_no_deja_tmp(tmp_path):
    state_mod.registrar_owner(5)
    # No deben quedar archivos .state.*.json.tmp huérfanos.
    tmps = list(tmp_path.glob(".state.*.json.tmp"))
    assert tmps == []


def test_es_owner_acepta_str_e_int():
    state_mod.registrar_owner(42)
    assert state_mod.es_owner(42) is True
    assert state_mod.es_owner("42") is True
