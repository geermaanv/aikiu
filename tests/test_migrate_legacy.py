"""
Tests para core/migrate_legacy.py — migración single-tenant → multi-tenant.

Cada test apunta BASE_DIR y AIKIU_REGISTRY a tmpdirs aislados.
"""

import json

import pytest

from core import hogar as hogar_mod
from core import migrate_legacy as migrate_mod


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """
    Simula un repo legacy en `tmp_path / "repo"` y un registry en
    `tmp_path / "registry"`. Devuelve los dos paths para que el test
    pueble el repo y verifique el registry.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    registry = tmp_path / "registry"
    registry.mkdir()

    monkeypatch.setattr(migrate_mod, "BASE_DIR", repo)
    monkeypatch.setattr(hogar_mod, "BASE_DIR", repo)
    monkeypatch.setenv("AIKIU_REGISTRY", str(registry))
    monkeypatch.delenv("CHAT_ID", raising=False)

    return repo, registry


# ---------------------------------------------------------------------------
# Casos noop
# ---------------------------------------------------------------------------

def test_migrar_sin_state_legacy_noop(fake_repo):
    repo, registry = fake_repo
    assert migrate_mod.migrar_si_corresponde() is None
    assert hogar_mod.listar_hogares() == []


def test_migrar_state_sin_owner_chat_id_noop(fake_repo):
    repo, _ = fake_repo
    (repo / "state.json").write_text(json.dumps({}), encoding="utf-8")
    assert migrate_mod.migrar_si_corresponde() is None
    assert hogar_mod.listar_hogares() == []


def test_migrar_idempotente_si_ya_hay_hogares(fake_repo):
    """Si ya existe al menos un hogar, no toca nada (segunda corrida es noop)."""
    repo, _ = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 42, "registered_at": "2026-01-01"}),
        encoding="utf-8",
    )
    primer = migrate_mod.migrar_si_corresponde()
    assert primer == 42
    # Segunda corrida: no hace nada (el legacy state.json ya fue movido)
    segundo = migrate_mod.migrar_si_corresponde()
    assert segundo is None


# ---------------------------------------------------------------------------
# Migración real
# ---------------------------------------------------------------------------

def test_migrar_state_legacy_crea_hogar(fake_repo):
    repo, registry = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 1234567, "registered_at": "2026-01-01"}),
        encoding="utf-8",
    )

    owner = migrate_mod.migrar_si_corresponde()
    assert owner == 1234567
    assert hogar_mod.existe_hogar(1234567)
    # El state.json viejo de la raíz ya no existe (movido)
    assert not (repo / "state.json").exists()
    # El nuevo está en instances/<chat_id>/state.json
    nuevo = registry / "1234567" / "state.json"
    assert nuevo.exists()


def test_migrar_mueve_perfil_stats_y_otros(fake_repo):
    repo, registry = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 42}), encoding="utf-8"
    )
    (repo / "perfil.md").write_text("# Perfil de Marta", encoding="utf-8")
    (repo / "stats.json").write_text(json.dumps({"2026-05-22": {"mensajes": 5}}), encoding="utf-8")
    (repo / "receptividad.json").write_text(json.dumps([{"tema": "tango"}]), encoding="utf-8")
    (repo / "familiares.json").write_text(json.dumps([{"chat_id": 99}]), encoding="utf-8")
    (repo / "usage.json").write_text(json.dumps([{"op": "chat"}]), encoding="utf-8")

    migrate_mod.migrar_si_corresponde()

    hogar = registry / "42"
    assert (hogar / "perfil.md").read_text(encoding="utf-8") == "# Perfil de Marta"
    assert json.loads((hogar / "stats.json").read_text(encoding="utf-8")) == {
        "2026-05-22": {"mensajes": 5}
    }
    assert json.loads((hogar / "receptividad.json").read_text(encoding="utf-8")) == [
        {"tema": "tango"}
    ]
    assert json.loads((hogar / "familiares.json").read_text(encoding="utf-8")) == [
        {"chat_id": 99}
    ]
    assert json.loads((hogar / "usage.json").read_text(encoding="utf-8")) == [
        {"op": "chat"}
    ]


def test_migrar_mueve_logs_diarios(fake_repo):
    repo, registry = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 42}), encoding="utf-8"
    )
    logs = repo / "logs"
    logs.mkdir()
    (logs / "2026-05-20.md").write_text("# log 20", encoding="utf-8")
    (logs / "2026-05-21.md").write_text("# log 21", encoding="utf-8")

    migrate_mod.migrar_si_corresponde()

    destino_logs = registry / "42" / "logs"
    assert (destino_logs / "2026-05-20.md").read_text(encoding="utf-8") == "# log 20"
    assert (destino_logs / "2026-05-21.md").read_text(encoding="utf-8") == "# log 21"
    # La carpeta vieja quedó vacía y se borró
    assert not logs.exists()


def test_migrar_mueve_heartbeats_pero_no_admin(fake_repo):
    repo, registry = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 42}), encoding="utf-8"
    )
    (repo / "heartbeat-aikiu.json").write_text("{}", encoding="utf-8")
    (repo / "heartbeat-familiar.json").write_text("{}", encoding="utf-8")
    (repo / "heartbeat-admin.json").write_text("{}", encoding="utf-8")

    migrate_mod.migrar_si_corresponde()

    hogar = registry / "42"
    assert (hogar / "heartbeat-aikiu.json").exists()
    assert (hogar / "heartbeat-familiar.json").exists()
    # admin se queda en la raíz (no es por instancia)
    assert (repo / "heartbeat-admin.json").exists()
    assert not (hogar / "heartbeat-admin.json").exists()


def test_migrar_no_pisa_archivos_existentes_en_destino(fake_repo):
    """Si por alguna razón ya hay algo en `instances/<owner>/`, no se sobreescribe."""
    repo, registry = fake_repo
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 42}), encoding="utf-8"
    )
    (repo / "perfil.md").write_text("# legacy perfil", encoding="utf-8")

    # Pre-creamos el hogar con un perfil distinto
    destino = registry / "42"
    destino.mkdir()
    (destino / "state.json").write_text(
        json.dumps({"owner_chat_id": 42, "pre_existente": True}),
        encoding="utf-8",
    )
    (destino / "perfil.md").write_text("# perfil pre-existente", encoding="utf-8")

    # listar_hogares() ahora ve el hogar pre-existente, así que migración es noop
    result = migrate_mod.migrar_si_corresponde()
    assert result is None
    # El perfil pre-existente se mantiene
    assert (destino / "perfil.md").read_text(encoding="utf-8") == "# perfil pre-existente"
    # El perfil legacy sigue en la raíz (no fue movido)
    assert (repo / "perfil.md").exists()


# ---------------------------------------------------------------------------
# Override por env CHAT_ID
# ---------------------------------------------------------------------------

def test_chat_id_env_override(fake_repo, monkeypatch):
    """Si CHAT_ID está seteada, gana sobre state.json — útil para installs que
    nunca persistieron state.json."""
    repo, registry = fake_repo
    monkeypatch.setenv("CHAT_ID", "777")
    # No hay state.json en raíz, pero hay CHAT_ID
    (repo / "perfil.md").write_text("# perfil", encoding="utf-8")

    owner = migrate_mod.migrar_si_corresponde()
    assert owner == 777
    assert (registry / "777" / "perfil.md").exists()


def test_chat_id_env_placeholder_ignorado(fake_repo, monkeypatch):
    repo, _ = fake_repo
    monkeypatch.setenv("CHAT_ID", "PEGA_TU_CHAT_ID")
    assert migrate_mod.migrar_si_corresponde() is None
