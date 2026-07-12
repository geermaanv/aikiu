"""
Tests del entrypoint main() de los 3 bots y de aikiu.cargar_config.
Mockeamos PTB Application para no abrir conexiones reales pero sí
ejercitamos los bloques completos.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aikiu
from admin import bot as admin_bot
from admin import state as admin_state
import familiar_bot
from core import state as state_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "admin_state.json")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", tmp_path / "legacy.json")
    for e in ("CHAT_ID", "ADMIN_CHAT_ID", "ADMIN_CHAT_IDS"):
        monkeypatch.delenv(e, raising=False)


# ===========================================================================
# aikiu.cargar_config — ramas faltantes (52, 58)
# ===========================================================================

def test_aikiu_cargar_config_falla_sin_bot_token(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "nombre_adulto_mayor: X\nnombre_asistente: Y\n", encoding="utf-8"
    )
    monkeypatch.setattr(aikiu, "BASE_DIR", tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_abc")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        aikiu.cargar_config()


def test_aikiu_cargar_config_falla_sin_groq(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "nombre_adulto_mayor: X\nnombre_asistente: Y\n", encoding="utf-8"
    )
    monkeypatch.setattr(aikiu, "BASE_DIR", tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "real:token")
    monkeypatch.setenv("GROQ_API_KEY", "PEGA_TU_KEY")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        aikiu.cargar_config()


def test_aikiu_cargar_config_sin_perfil_file(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "nombre_adulto_mayor: X\nnombre_asistente: Y\nperfil: no_existe.md\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(aikiu, "BASE_DIR", tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "real:token")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_abc")
    out = aikiu.cargar_config()
    assert out["_perfil"] == ""


def test_aikiu_cargar_config_con_perfil_file(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "nombre_adulto_mayor: X\nnombre_asistente: Y\nperfil: perfil.md\n",
        encoding="utf-8",
    )
    (tmp_path / "perfil.md").write_text("contenido aprendido", encoding="utf-8")
    monkeypatch.setattr(aikiu, "BASE_DIR", tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "real:token")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_abc")
    out = aikiu.cargar_config()
    assert "contenido aprendido" in out["_perfil"]


# ===========================================================================
# aikiu._alertar_sintomas_persistentes — rama de error de envío (658-662)
# ===========================================================================

def test_alertar_sintomas_envio_falla(monkeypatch, tmp_path):
    """Síntomas detectados ayer+hoy, family_bot configurado pero send_message rompe."""
    from datetime import date, timedelta
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path)
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (tmp_path / f"{ayer}.md").write_text("me duele la rodilla", encoding="utf-8")
    family_bot = MagicMock()
    family_bot.send_message = AsyncMock(side_effect=RuntimeError("bloqueado"))
    app = MagicMock()
    app.bot_data = {"family_bot": family_bot}
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "Marta",
                                          "nombre_asistente": "Aikiu"})
    with patch("core.alerts.cargar_suscriptores", return_value=[999]):
        run(aikiu._alertar_sintomas_persistentes(app, "hoy también me duele la rodilla"))
    family_bot.send_message.assert_awaited_once()


def test_alertar_sintomas_excepcion_global(monkeypatch, tmp_path):
    """Si cargar_suscriptores explota, el try externo lo absorbe."""
    from datetime import date, timedelta
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path)
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (tmp_path / f"{ayer}.md").write_text("dolor", encoding="utf-8")
    app = MagicMock()
    app.bot_data = {"family_bot": MagicMock()}
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "M", "nombre_asistente": "C"})
    with patch("core.alerts.cargar_suscriptores", side_effect=RuntimeError("io")):
        run(aikiu._alertar_sintomas_persistentes(app, "dolor de cabeza"))


def test_alertar_sintomas_sin_persistentes_retorna(monkeypatch, tmp_path):
    """Si no hay overlap entre hoy y ayer, no llama family_bot."""
    from datetime import date, timedelta
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path)
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (tmp_path / f"{ayer}.md").write_text("rodilla", encoding="utf-8")
    fam = MagicMock()
    fam.send_message = AsyncMock()
    app = MagicMock()
    app.bot_data = {"family_bot": fam}
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "M", "nombre_asistente": "C"})
    run(aikiu._alertar_sintomas_persistentes(app, "todo bien hoy"))
    fam.send_message.assert_not_awaited()


def test_alertar_sintomas_sin_log_ayer(monkeypatch, tmp_path):
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path)
    run(aikiu._alertar_sintomas_persistentes(MagicMock(), "dolor"))


def test_alertar_sintomas_persistentes_pero_sin_family_bot(monkeypatch, tmp_path):
    from datetime import date, timedelta
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path)
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (tmp_path / f"{ayer}.md").write_text("dolor de espalda", encoding="utf-8")
    app = MagicMock()
    app.bot_data = {}  # sin family_bot
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "M", "nombre_asistente": "C"})
    run(aikiu._alertar_sintomas_persistentes(app, "dolor de espalda"))


# ===========================================================================
# aikiu._calcular_ranking_temas — ts inválido (línea 450)
# ===========================================================================

def test_calcular_ranking_ignora_ts_invalido(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", tmp_path / "recep.json")
    import json
    aikiu.RECEPTIVIDAD_PATH.write_text(json.dumps([
        {"tema": "X", "receptividad": "alta", "palabras_usuario": 10, "ts": "no-iso"},
    ]), encoding="utf-8")
    ranking = aikiu._calcular_ranking_temas()
    # ts inválido se ignora → no quedan temas con score
    assert ranking == []


# ===========================================================================
# aikiu.main() — entrypoint completo (1003-1050)
# ===========================================================================

class FakeBot:
    def __init__(self):
        self.send_chat_action = AsyncMock()
        self.send_message = AsyncMock()
        self.set_my_commands = AsyncMock()

class FakeUpdater:
    def __init__(self):
        self.start_polling = AsyncMock()
        self.stop = AsyncMock()

class FakeApp:
    def __init__(self):
        self.bot = FakeBot()
        self.bot_data = {}
        self.updater = FakeUpdater()
        self._handlers = []
    def add_handler(self, h):
        self._handlers.append(h)
    def add_error_handler(self, h):
        self._error_handler = h
    async def initialize(self): pass
    async def start(self): pass
    async def stop(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


def test_aikiu_main_arranca_y_para(monkeypatch):
    monkeypatch.setattr(aikiu, "CONFIG", {
        "nombre_adulto_mayor": "Marta",
        "nombre_asistente": "Aikiu",
        "bot_token": "real:token",
        "modelo_llm": "m",
    })

    fake_app = FakeApp()
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(aikiu.Application, "builder", lambda: fake_builder)

    # Scheduler no real
    sched_mock = MagicMock()
    sched_mock.start = MagicMock()
    sched_mock.shutdown = MagicMock()
    monkeypatch.setattr(aikiu, "AsyncIOScheduler", lambda: sched_mock)

    # Heartbeat
    monkeypatch.setattr(aikiu.hb_mod, "iniciar_heartbeat", lambda role: None)
    monkeypatch.setattr(aikiu, "programar_recordatorios", lambda s, a: None)

    # Familiar token presente
    monkeypatch.setenv("FAMILIAR_BOT_TOKEN", "fam:token")

    # Reemplazar Event().wait() para que retorne inmediatamente
    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(aikiu.asyncio, "Event", lambda: FakeEvent())

    # Bot familiar mock
    monkeypatch.setattr(aikiu, "Bot", MagicMock(return_value=MagicMock()))

    run(aikiu.main())
    # Verificaciones
    assert len(fake_app._handlers) == 3  # start + invitar + message handler
    assert "family_bot" in fake_app.bot_data
    sched_mock.start.assert_called_once()
    sched_mock.shutdown.assert_called_once()


def test_aikiu_main_sin_familiar_token(monkeypatch):
    monkeypatch.setattr(aikiu, "CONFIG", {
        "nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
        "bot_token": "real:token", "modelo_llm": "m",
    })
    fake_app = FakeApp()
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(aikiu.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(aikiu, "AsyncIOScheduler", lambda: MagicMock(
        start=MagicMock(), shutdown=MagicMock()))
    monkeypatch.setattr(aikiu.hb_mod, "iniciar_heartbeat", lambda role: None)
    monkeypatch.setattr(aikiu, "programar_recordatorios", lambda s, a: None)
    monkeypatch.setenv("FAMILIAR_BOT_TOKEN", "PEGA_TU_TOKEN")

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(aikiu.asyncio, "Event", lambda: FakeEvent())

    # Owner registrado (otra rama del log)
    state_mod.registrar_owner(42)

    run(aikiu.main())
    assert "family_bot" not in fake_app.bot_data


# ===========================================================================
# admin/bot.py main() — entrypoint (1164-1211)
# ===========================================================================

def test_admin_main_falla_sin_token(monkeypatch):
    monkeypatch.setattr(admin_bot, "ADMIN_TOKEN", "")
    with pytest.raises(RuntimeError, match="ADMIN_BOT_TOKEN"):
        run(admin_bot.main())


def test_admin_main_arranca_sin_admins(monkeypatch):
    monkeypatch.setattr(admin_bot, "ADMIN_TOKEN", "real:token")
    fake_app = FakeApp()
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(admin_bot.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(admin_bot.hb_mod, "iniciar_heartbeat",
                        lambda role, dir_override=None: None)

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(admin_bot.asyncio, "Event", lambda: FakeEvent())

    run(admin_bot.main())
    # Se registraron 12 handlers (10 originales + hogares + borrar)
    assert len(fake_app._handlers) == 12


def test_admin_main_con_admins(monkeypatch):
    monkeypatch.setattr(admin_bot, "ADMIN_TOKEN", "real:token")
    admin_state.registrar_admin(7)
    admin_state.registrar_admin(8)
    fake_app = FakeApp()
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(admin_bot.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(admin_bot.hb_mod, "iniciar_heartbeat",
                        lambda role, dir_override=None: None)

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(admin_bot.asyncio, "Event", lambda: FakeEvent())

    run(admin_bot.main())
    assert len(fake_app._handlers) == 12


def test_admin_main_publicar_comandos_falla(monkeypatch):
    monkeypatch.setattr(admin_bot, "ADMIN_TOKEN", "real:token")
    fake_app = FakeApp()
    fake_app.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("net"))
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(admin_bot.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(admin_bot.hb_mod, "iniciar_heartbeat",
                        lambda role, dir_override=None: None)

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(admin_bot.asyncio, "Event", lambda: FakeEvent())

    # No debería propagar
    run(admin_bot.main())


# ===========================================================================
# familiar_bot.main() — entrypoint completo
# ===========================================================================

def test_familiar_main_arranca(monkeypatch):
    monkeypatch.setattr(familiar_bot, "FAMILIAR_TOKEN", "real:token")
    fake_app = FakeApp()
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(familiar_bot.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(familiar_bot.hb_mod, "iniciar_heartbeat",
                        lambda role: None)

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(familiar_bot.asyncio, "Event", lambda: FakeEvent())

    run(familiar_bot.main())
    # 7 CommandHandlers + 2 ConversationHandler = 9
    assert len(fake_app._handlers) >= 9


def test_familiar_main_publicar_comandos_falla(monkeypatch):
    monkeypatch.setattr(familiar_bot, "FAMILIAR_TOKEN", "real:token")
    fake_app = FakeApp()
    fake_app.bot.set_my_commands = AsyncMock(side_effect=RuntimeError("net"))
    fake_builder = MagicMock()
    fake_builder.token = MagicMock(return_value=fake_builder)
    fake_builder.build = MagicMock(return_value=fake_app)
    monkeypatch.setattr(familiar_bot.Application, "builder", lambda: fake_builder)
    monkeypatch.setattr(familiar_bot.hb_mod, "iniciar_heartbeat", lambda role: None)

    class FakeEvent:
        async def wait(self): return None
    monkeypatch.setattr(familiar_bot.asyncio, "Event", lambda: FakeEvent())

    run(familiar_bot.main())  # no raise


# ===========================================================================
# admin/bot._tail_lineas filtrando errores (1055-1056)
# ===========================================================================

def test_admin_tail_filtra_solo_errores(tmp_path):
    log = tmp_path / "x.log"
    log.write_text(
        "2025-01-01 [INFO] linea info ok\n"
        "2025-01-01 [ERROR] algo se rompio\n"
        "2025-01-01 [WARNING] ojo\n"
        "2025-01-01 [INFO] bla\n"
        "2025-01-01 [ERROR] otro\n",
        encoding="utf-8",
    )
    out = admin_bot._tail_lineas(log, 10, solo_errores=True)
    assert any("[ERROR]" in l for l in out)
    assert not any("info ok" in l for l in out)


def test_admin_tail_no_existe_devuelve_vacio(tmp_path):
    assert admin_bot._tail_lineas(tmp_path / "no.log", 10) == []


def test_admin_tail_lee_archivo_completo(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
    out = admin_bot._tail_lineas(log, 3)
    assert out == ["c", "d", "e"]
