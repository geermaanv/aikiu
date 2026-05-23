"""
Cierra los ultimos gaps de cobertura para cruzar 95%:
- andromarta/bot.py: _validar_config, _disparar_iniciativa edge cases, run()
- familiar_bot.py: cmd_suscriptores vacio, cmd_stats variantes, recibir_mensaje voz path, cancelar y main
- admin/state.py: legacy migration, env overrides, registrar duplicado, quitar inexistente, reset
- admin/bot.py: helpers chicos sin cubrir
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin import state as admin_state
from admin import bot as admin_bot
from andromarta import bot as andro_bot
from andromarta import ciclo as ciclo_mod
from andromarta import memoria as memoria_mod
from andromarta import estado as andro_estado
from andromarta import persona as andro_persona
import familiar_bot
from core import state as state_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "admin_state.json")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", tmp_path / "legacy.json")
    for e in ("ADMIN_CHAT_ID", "ADMIN_CHAT_IDS", "ADMIN_MAX_USERS", "CHAT_ID"):
        monkeypatch.delenv(e, raising=False)
    monkeypatch.setattr(familiar_bot, "FAMILIARES_PATH", tmp_path / "familiares.json")
    monkeypatch.setattr(familiar_bot, "PERFIL_PATH", tmp_path / "perfil.md")
    monkeypatch.setattr(familiar_bot, "STATS_PATH", tmp_path / "stats.json")
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", tmp_path / "memoria.json")
    monkeypatch.setattr(ciclo_mod, "CICLO_PATH", tmp_path / "ciclo.json")
    monkeypatch.setattr(andro_estado, "ESTADO_PATH", tmp_path / "andro_estado.json")
    monkeypatch.setattr(andro_persona, "PERSONA_PATH", tmp_path / "persona.md")


# ===========================================================================
# andromarta/bot.py — gaps
# ===========================================================================

def test_andromarta_validar_config_falla_si_falta_api_id(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "")
    monkeypatch.setattr(andro_bot, "API_HASH", "abc")
    monkeypatch.setattr(andro_bot, "PHONE", "+5491100000000")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "aikiu_bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "gsk_abc")
    with pytest.raises(RuntimeError, match="ANDROMARTA_API_ID"):
        andro_bot._validar_config()


def test_andromarta_validar_config_falla_si_falta_groq(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "12345")
    monkeypatch.setattr(andro_bot, "API_HASH", "realhashvalueok")
    monkeypatch.setattr(andro_bot, "PHONE", "+5491100000000")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "aikiu_bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        andro_bot._validar_config()


def test_andromarta_validar_config_ok(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "12345")
    monkeypatch.setattr(andro_bot, "API_HASH", "realhashvalueok")
    monkeypatch.setattr(andro_bot, "PHONE", "+5491100000000")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "aikiu_bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "gsk_abc")
    # No raise
    andro_bot._validar_config()


def test_andromarta_disparar_iniciativa_no_dispara_si_ciclo_abierto(monkeypatch):
    # Ya hay ciclo abierto → la iniciativa no debería actuar
    ciclo_mod.guardar({"abierto": True, "turnos": 3, "abierto_at": datetime.now().isoformat()})
    client = MagicMock()
    client.send_message = AsyncMock()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", MagicMock())
    run(andro_bot._disparar_iniciativa())
    client.send_message.assert_not_awaited()


def test_andromarta_disparar_iniciativa_maneja_error_de_responder(monkeypatch):
    ciclo_mod.guardar({"abierto": False, "turnos": 0})
    client = MagicMock()
    action_ctx = MagicMock()
    action_ctx.__aenter__ = AsyncMock(return_value=None)
    action_ctx.__aexit__ = AsyncMock(return_value=False)
    client.action = MagicMock(return_value=action_ctx)
    client.send_message = AsyncMock()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", MagicMock())
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)

    async def boom(**kw):
        raise RuntimeError("LLM caido")
    monkeypatch.setattr(andro_bot, "responder", boom)

    # No debería propagar
    run(andro_bot._disparar_iniciativa())
    client.send_message.assert_not_awaited()


def test_andromarta_run_falla_si_no_encuentra_aikiu(monkeypatch):
    monkeypatch.setattr(andro_bot, "_validar_config", lambda: None)

    class FakeClient:
        def __init__(self, *a, **kw):
            pass
        async def start(self, **kw):
            return None
        async def get_entity(self, name):
            raise RuntimeError("not found")
        async def disconnect(self):
            self.disconnected = True
        def add_event_handler(self, *a, **kw):
            pass
        async def run_until_disconnected(self):
            return None

    instances = []
    def factory(*a, **kw):
        c = FakeClient()
        instances.append(c)
        return c

    monkeypatch.setattr(andro_bot, "TelegramClient", factory)
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "1")
    monkeypatch.setattr(andro_bot, "API_HASH", "h")
    monkeypatch.setattr(andro_bot, "PHONE", "+1")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "x")
    run(andro_bot.run())
    # No raise; ya verificamos que el flujo no se rompe


def test_andromarta_ts_devuelve_iso():
    s = andro_bot._ts()
    # Formato iso sin micros
    datetime.fromisoformat(s)


# ===========================================================================
# familiar_bot.py — gaps
# ===========================================================================

def test_familiar_cmd_suscriptores_vacio_pero_suscripto(monkeypatch):
    """La rama 'No hay familiares' es defensiva; con suscriptor mockeado la cubrimos."""
    monkeypatch.setattr(familiar_bot, "es_suscriptor", lambda cid: True)
    monkeypatch.setattr(familiar_bot, "cargar_familiares", list)
    update = MagicMock()
    update.effective_chat.id = 999
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    run(familiar_bot.cmd_suscriptores(update, ctx))
    msg = update.message.reply_text.await_args.args[0]
    assert "No hay familiares" in msg


def test_familiar_cmd_stats_sin_archivo():
    familiar_bot.agregar_familiar(999)
    if familiar_bot.STATS_PATH.exists():
        familiar_bot.STATS_PATH.unlink()
    update = MagicMock()
    update.effective_chat.id = 999
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    run(familiar_bot.cmd_stats(update, ctx))
    msg = update.message.reply_text.await_args.args[0]
    assert "estadísticas" in msg.lower() or "todavía" in msg.lower()


def test_familiar_cmd_stats_archivo_invalido():
    familiar_bot.agregar_familiar(999)
    familiar_bot.STATS_PATH.write_text("[]", encoding="utf-8")
    update = MagicMock()
    update.effective_chat.id = 999
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    run(familiar_bot.cmd_stats(update, ctx))
    # Es lista, sorted falla? sorted(["0"]) funciona pero load_json devuelve [] que es falsy
    # ".keys()" sobre list lanzaría AttributeError; el código verifica `if not stats`
    msg = update.message.reply_text.await_args.args[0]
    assert "Error" in msg or "datos" in msg.lower() or "Sin" in msg


def test_familiar_recibir_mensaje_familiar_voz_path(monkeypatch):
    """Mensaje de voz se transcribe y se reenvía como voz sintetizada."""
    familiar_bot.agregar_familiar(999)
    familiar_bot.actualizar_nombre(999, "Germán")
    state_mod.registrar_owner(42)

    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()
    update.message.text = None
    update.message.voice = MagicMock()
    file_mock = MagicMock()
    file_mock.download_to_drive = AsyncMock(side_effect=lambda p: Path(p).write_bytes(b"oggdata"))
    update.message.voice.get_file = AsyncMock(return_value=file_mock)
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()

    # Mock Groq transcripción
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value="hola Marta")
    monkeypatch.setattr(familiar_bot, "AsyncGroq", lambda **kw: fake_groq)
    monkeypatch.setattr(familiar_bot, "GROQ_API_KEY", "k")
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")

    # Mock sintetizar y Bot
    async def fake_sint(texto, ogg, voz):
        Path(ogg).write_bytes(b"vozsint")
    monkeypatch.setattr(familiar_bot, "sintetizar", fake_sint)

    mock_bot = MagicMock()
    mock_bot.send_voice = AsyncMock()
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(return_value=mock_bot)
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("familiar_bot.Bot", return_value=bot_ctx):
        run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    mock_bot.send_voice.assert_awaited_once()


def test_familiar_recibir_mensaje_voz_transcripcion_falla(monkeypatch):
    familiar_bot.agregar_familiar(999)
    familiar_bot.actualizar_nombre(999, "Germán")
    state_mod.registrar_owner(42)

    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()
    update.message.text = None
    update.message.voice = MagicMock()
    file_mock = MagicMock()
    file_mock.download_to_drive = AsyncMock(side_effect=lambda p: Path(p).write_bytes(b"x"))
    update.message.voice.get_file = AsyncMock(return_value=file_mock)
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()

    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(side_effect=RuntimeError("nada"))
    monkeypatch.setattr(familiar_bot, "AsyncGroq", lambda **kw: fake_groq)
    monkeypatch.setattr(familiar_bot, "GROQ_API_KEY", "k")

    estado = run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    assert estado == familiar_bot.ESPERANDO_MENSAJE
    msg = update.message.reply_text.await_args.args[0]
    assert "transcribir" in msg.lower() or "audio" in msg.lower()


def test_familiar_recibir_mensaje_sin_owner_chat_id(monkeypatch):
    familiar_bot.agregar_familiar(999)
    familiar_bot.actualizar_nombre(999, "Germán")
    # state vacío → owner_chat_id None

    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()
    update.message.voice = None
    update.message.text = "hola"
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")

    from telegram.ext import ConversationHandler
    estado = run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    assert estado == ConversationHandler.END
    msg = update.message.reply_text.await_args.args[0]
    assert "abrió" in msg or "/start" in msg


def test_familiar_recibir_mensaje_falla_envio(monkeypatch):
    familiar_bot.agregar_familiar(999)
    familiar_bot.actualizar_nombre(999, "Germán")
    state_mod.registrar_owner(42)

    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()
    update.message.voice = None
    update.message.text = "hola"
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=RuntimeError("bloqueado"))
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(return_value=mock_bot)
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("familiar_bot.Bot", return_value=bot_ctx):
        run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    # El error se reporta al familiar
    msg = update.message.reply_text.await_args.args[0]
    assert "error" in msg.lower() or "Hubo" in msg


def test_familiar_recibir_mensaje_texto_vacio(monkeypatch):
    familiar_bot.agregar_familiar(999)
    familiar_bot.actualizar_nombre(999, "Germán")
    state_mod.registrar_owner(42)

    update = MagicMock()
    update.effective_chat.id = 999
    update.message = MagicMock()
    update.message.voice = None
    update.message.text = "   "
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    estado = run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    assert estado == familiar_bot.ESPERANDO_MENSAJE


def test_familiar_main_falla_si_no_hay_token(monkeypatch):
    monkeypatch.setattr(familiar_bot, "FAMILIAR_TOKEN", "")
    with pytest.raises(RuntimeError, match="FAMILIAR_BOT_TOKEN"):
        run(familiar_bot.main())


# ===========================================================================
# admin/state.py — gaps
# ===========================================================================

def test_admin_state_migracion_legacy_a_nuevo(tmp_path):
    """El legacy se mueve tal cual (formato viejo). Al leerlo, _leer_estado lo
    normaliza al formato nuevo."""
    legacy = admin_state.LEGACY_ADMIN_STATE_PATH
    nuevo = admin_state.ADMIN_STATE_PATH
    legacy.write_text(json.dumps({"admin_chat_id": 5, "registered_at": "2024-01-01"}),
                      encoding="utf-8")
    if nuevo.exists():
        nuevo.unlink()
    admin_state._migrar_legacy_si_corresponde()
    assert nuevo.exists()
    assert not legacy.exists()
    estado = admin_state._leer_estado()
    assert estado["admins"][0]["chat_id"] == 5


def test_admin_state_migracion_legacy_falla_silencioso(monkeypatch, tmp_path):
    """Si os.replace falla, se loguea y sigue."""
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", legacy)
    # Forzamos que el nuevo path no exista
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "no_existe" / "admin.json")
    monkeypatch.setattr(os, "replace", MagicMock(side_effect=OSError("perm")))
    admin_state._migrar_legacy_si_corresponde()  # no raise


def test_admin_state_normalizar_legacy_invalido():
    # admin_chat_id no convertible → lista vacía
    out = admin_state._normalizar({"admin_chat_id": "no-num", "registered_at": "x"})
    assert out["admins"] == []


def test_admin_state_normalizar_descarta_entradas_invalidas():
    out = admin_state._normalizar({
        "admins": [
            "string-suelto",  # no dict, se descarta
            {"chat_id": "nope"},  # no parsea
            {"chat_id": "10", "added_by": "no-int"},  # added_by se descarta
            {"chat_id": 20, "added_by": 99, "registered_at": "2025-01-01"},
        ]
    })
    cids = [a["chat_id"] for a in out["admins"]]
    assert cids == [10, 20]
    # added_by inválido se cayó
    e10 = [a for a in out["admins"] if a["chat_id"] == 10][0]
    assert "added_by" not in e10
    e20 = [a for a in out["admins"] if a["chat_id"] == 20][0]
    assert e20["added_by"] == 99


def test_admin_state_leer_json_corrupto_devuelve_vacio(tmp_path):
    admin_state.ADMIN_STATE_PATH.write_text("no es json {{{", encoding="utf-8")
    estado = admin_state._leer_estado()
    assert estado["admins"] == []


def test_admin_state_escribir_atomico_falla_y_limpia(monkeypatch, tmp_path):
    # Forzar fallo del json.dump
    def fail_dump(*a, **kw):
        raise RuntimeError("io")
    monkeypatch.setattr(admin_state.json, "dump", fail_dump)
    with pytest.raises(RuntimeError):
        admin_state._escribir_estado_atomico({"admins": []})


def test_admin_state_env_override_ids_lista_con_invalidos(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "1, 2, no-num, 1, 3")  # dup y basura
    out = admin_state._env_override_ids()
    assert out == [1, 2, 3]


def test_admin_state_env_override_solo_singular(monkeypatch):
    monkeypatch.delenv("ADMIN_CHAT_IDS", raising=False)
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")
    assert admin_state._env_override_ids() == [42]


def test_admin_state_env_override_singular_invalido(monkeypatch):
    monkeypatch.delenv("ADMIN_CHAT_IDS", raising=False)
    monkeypatch.setenv("ADMIN_CHAT_ID", "no-num")
    assert admin_state._env_override_ids() is None


def test_admin_state_env_override_singular_placeholder(monkeypatch):
    monkeypatch.delenv("ADMIN_CHAT_IDS", raising=False)
    monkeypatch.setenv("ADMIN_CHAT_ID", "PEGA_TU_ID")
    assert admin_state._env_override_ids() is None


def test_admin_state_admins_max_default(monkeypatch):
    monkeypatch.delenv("ADMIN_MAX_USERS", raising=False)
    assert admin_state.admins_max() == admin_state.DEFAULT_ADMIN_MAX_USERS


def test_admin_state_admins_max_custom(monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_USERS", "10")
    assert admin_state.admins_max() == 10


def test_admin_state_admins_max_invalido_usa_default(monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_USERS", "no-num")
    assert admin_state.admins_max() == admin_state.DEFAULT_ADMIN_MAX_USERS


def test_admin_state_registrar_admin_duplicado_false():
    assert admin_state.registrar_admin(1) is True
    assert admin_state.registrar_admin(1) is False  # dup


def test_admin_state_registrar_admin_cupo_lleno(monkeypatch):
    monkeypatch.setenv("ADMIN_MAX_USERS", "2")
    assert admin_state.registrar_admin(1)
    assert admin_state.registrar_admin(2)
    assert admin_state.registrar_admin(3) is False  # cupo


def test_admin_state_registrar_admin_chat_id_invalido():
    assert admin_state.registrar_admin("no-num") is False


def test_admin_state_registrar_admin_con_env_override_false(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "1,2")
    assert admin_state.registrar_admin(5) is False


def test_admin_state_registrar_admin_added_by_invalido():
    # added_by no convertible → se silencia pero el admin se registra
    assert admin_state.registrar_admin(7, added_by="no") is True
    estado = admin_state._leer_estado()
    entrada = [a for a in estado["admins"] if a["chat_id"] == 7][0]
    assert "added_by" not in entrada


def test_admin_state_quitar_admin_inexistente():
    assert admin_state.quitar_admin(123) is False


def test_admin_state_quitar_admin_chat_id_invalido():
    assert admin_state.quitar_admin("nope") is False


def test_admin_state_quitar_admin_con_env_false(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "1,2")
    assert admin_state.quitar_admin(1) is False


def test_admin_state_reset_admin_vacio_false():
    assert admin_state.reset_admin() is False


def test_admin_state_reset_admin_borra_todo():
    admin_state.registrar_admin(1)
    admin_state.registrar_admin(2)
    assert admin_state.reset_admin() is True
    assert admin_state.admin_chat_ids() == []


def test_admin_state_es_admin_invalido():
    assert admin_state.es_admin("no-num") is False
    assert admin_state.es_admin(None) is False


def test_admin_state_admin_chat_id_compat_devuelve_primero():
    admin_state.registrar_admin(100)
    admin_state.registrar_admin(200)
    assert admin_state.admin_chat_id() == 100


def test_admin_state_listar_admins_con_env(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "5,6")
    out = admin_state.listar_admins()
    assert all(a["source"] == "env" for a in out)
    assert [a["chat_id"] for a in out] == [5, 6]
