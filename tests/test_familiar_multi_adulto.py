"""
Tests del flujo multi-adulto del bot familiar:
- /vincular con código de invitación
- /misadultos
- /elegir
- comandos legacy operando sobre el adulto activo
- notify_family con prefijo de adulto
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import familiar_bot
from core import familiar_state as fs
from core import hogar as hogar_mod
from core import invites as invites_mod
from core import state as state_mod
from core import alerts as alerts_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path / "registry"))
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(familiar_bot, "FAMILIARES_PATH", tmp_path / "familiares.json")
    monkeypatch.setattr(familiar_bot, "PERFIL_PATH", tmp_path / "perfil.md")
    monkeypatch.setattr(familiar_bot, "STATS_PATH", tmp_path / "stats.json")
    monkeypatch.delenv("CHAT_ID", raising=False)
    yield


def _fake_update(chat_id, first_name="Lao", text=""):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.text = text
    update.message.voice = None
    update.message.reply_text = AsyncMock()
    return update


def _fake_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    return ctx


# ---------------------------------------------------------------------------
# /vincular
# ---------------------------------------------------------------------------

def test_vincular_con_codigo_valido_vincula_y_anuncia():
    hogar_mod.crear_hogar(42, nombre="Marta")
    run(familiar_bot.cmd_start(_fake_update(101, first_name="Lao"), _fake_context()))
    codigo = invites_mod.generar_codigo(42)
    update = _fake_update(101, first_name="Lao")
    run(familiar_bot.cmd_vincular(update, _fake_context(args=[codigo])))
    assert fs.adultos_de(101) == [42]
    msg = update.message.reply_text.await_args.args[0]
    assert "vinculado" in msg.lower()
    # El código quedó consumido
    assert invites_mod.consumir(codigo) is None


def test_vincular_codigo_invalido_avisa():
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    update = _fake_update(101)
    run(familiar_bot.cmd_vincular(update, _fake_context(args=["NOEXISTE"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "no es válido" in msg or "expiró" in msg
    assert fs.adultos_de(101) == []


def test_vincular_sin_args_muestra_uso():
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    update = _fake_update(101)
    run(familiar_bot.cmd_vincular(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "vincular" in msg.lower()


def test_vincular_normaliza_codigo_a_mayusculas():
    hogar_mod.crear_hogar(42)
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    codigo = invites_mod.generar_codigo(42)
    update = _fake_update(101)
    run(familiar_bot.cmd_vincular(update, _fake_context(args=[codigo.lower()])))
    assert fs.adultos_de(101) == [42]


def test_vincular_dos_adultos_distintos_acumula():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    c1 = invites_mod.generar_codigo(42)
    c2 = invites_mod.generar_codigo(99)
    run(familiar_bot.cmd_vincular(_fake_update(101), _fake_context(args=[c1])))
    run(familiar_bot.cmd_vincular(_fake_update(101), _fake_context(args=[c2])))
    assert sorted(fs.adultos_de(101)) == [42, 99]


# ---------------------------------------------------------------------------
# /misadultos
# ---------------------------------------------------------------------------

def test_misadultos_sin_vinculos_sugiere_vincular():
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    # Aseguramos que hay al menos un hogar para que pida vincular
    hogar_mod.crear_hogar(42)
    update = _fake_update(101)
    run(familiar_bot.cmd_misadultos(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "vincular" in msg.lower()


def test_misadultos_con_un_adulto_lista_y_marca_activo():
    hogar_mod.crear_hogar(42, nombre="Marta")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42, nombre="Lao")
    update = _fake_update(101)
    run(familiar_bot.cmd_misadultos(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "42" in msg
    assert "activo" in msg.lower()


def test_misadultos_con_dos_adultos_y_uno_activo():
    hogar_mod.crear_hogar(42, nombre="Marta")
    hogar_mod.crear_hogar(99, nombre="Pepe")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, 99)
    update = _fake_update(101)
    run(familiar_bot.cmd_misadultos(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "Pepe" in msg
    # El activo se indica explícitamente
    assert "elegir" in msg.lower()


# ---------------------------------------------------------------------------
# /elegir
# ---------------------------------------------------------------------------

def test_elegir_sin_args_lista_opciones():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    fs.setear_adulto_activo(101, None)
    update = _fake_update(101)
    run(familiar_bot.cmd_elegir(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/elegir 42" in msg
    assert "/elegir 99" in msg


def test_elegir_con_adulto_valido_setea_activo():
    hogar_mod.crear_hogar(42, nombre="Marta")
    hogar_mod.crear_hogar(99, nombre="Pepe")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)
    fs.vincular(101, 99)
    update = _fake_update(101)
    run(familiar_bot.cmd_elegir(update, _fake_context(args=["99"])))
    assert fs.adulto_activo(101) == 99
    msg = update.message.reply_text.await_args.args[0]
    assert "Pepe" in msg


def test_elegir_adulto_al_que_no_estas_vinculado_rechaza():
    hogar_mod.crear_hogar(42)
    hogar_mod.crear_hogar(99)
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)
    update = _fake_update(101)
    run(familiar_bot.cmd_elegir(update, _fake_context(args=["99"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "no estás vinculado" in msg.lower()
    assert fs.adulto_activo(101) == 42


def test_elegir_arg_no_numerico_rechaza():
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    update = _fake_update(101)
    run(familiar_bot.cmd_elegir(update, _fake_context(args=["abc"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "número" in msg or "chat_id" in msg


# ---------------------------------------------------------------------------
# Comandos legacy operando sobre el adulto activo
# ---------------------------------------------------------------------------

def test_cmd_perfil_lee_del_adulto_activo_no_del_legacy():
    hogar_mod.crear_hogar(42, nombre="Marta")
    perfil_path_42 = hogar_mod.perfil_path(42)
    perfil_path_42.write_text("# Perfil de Marta\nContenido de Marta", encoding="utf-8")
    # El perfil legacy global tiene otra cosa
    familiar_bot.PERFIL_PATH.write_text("LEGACY", encoding="utf-8")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)

    update = _fake_update(101)
    run(familiar_bot.cmd_perfil(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "LEGACY" not in msg


def test_cmd_stats_lee_del_adulto_activo():
    hogar_mod.crear_hogar(42, nombre="Marta")
    stats_path_42 = hogar_mod.stats_path(42)
    stats_path_42.parent.mkdir(parents=True, exist_ok=True)
    stats_path_42.write_text(json.dumps({
        "2026-05-22": {
            "mensajes": 7,
            "primer_mensaje": "09:00",
            "ultimo_mensaje": "21:00",
            "distress": {"1": 0, "2": 0, "3": 0},
            "analisis_nocturno": {"aprendizajes_nuevos": 0},
        }
    }), encoding="utf-8")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42)

    update = _fake_update(101)
    run(familiar_bot.cmd_stats(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "7" in msg


def test_cmd_suscriptores_lee_del_adulto_activo():
    hogar_mod.crear_hogar(42, nombre="Marta")
    fams_42_path = hogar_mod.familiares_path(42)
    fams_42_path.parent.mkdir(parents=True, exist_ok=True)
    fams_42_path.write_text(json.dumps([
        {"chat_id": 101, "nombre": "Lao"},
        {"chat_id": 202, "nombre": "Ana"},
    ]), encoding="utf-8")
    run(familiar_bot.cmd_start(_fake_update(101), _fake_context()))
    fs.vincular(101, 42, nombre="Lao")

    update = _fake_update(101)
    run(familiar_bot.cmd_suscriptores(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Lao" in msg
    assert "Ana" in msg


# ---------------------------------------------------------------------------
# notify_family con adulto_chat_id
# ---------------------------------------------------------------------------

def test_notify_family_usa_familiares_del_hogar(monkeypatch):
    hogar_mod.crear_hogar(42, nombre="Marta")
    # Familiar suscripto al hogar 42 (no al legacy)
    fams_path = hogar_mod.familiares_path(42)
    fams_path.parent.mkdir(parents=True, exist_ok=True)
    fams_path.write_text(json.dumps([{"chat_id": 101, "nombre": "Lao"}]), encoding="utf-8")

    bot = MagicMock()
    bot.send_message = AsyncMock()

    run(alerts_mod.notify_family(
        distress_level=3,
        adulto_message="hola",
        bot_response="me llevo bien",
        family_bot=bot,
        adulto_chat_id=42,
    ))
    bot.send_message.assert_awaited()
    args = bot.send_message.await_args
    # El mensaje incluye al chat_id correcto y el nombre del adulto del hogar
    assert args.kwargs["chat_id"] == 101
    texto = args.kwargs["text"]
    assert "Marta" in texto
