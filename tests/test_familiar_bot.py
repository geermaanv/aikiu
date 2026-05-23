"""Tests para familiar_bot.py — handlers del bot familiar y helpers."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import familiar_bot
from core import state as state_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar_paths(tmp_path, monkeypatch):
    fam = tmp_path / "familiares.json"
    perfil = tmp_path / "perfil.md"
    stats = tmp_path / "stats.json"
    monkeypatch.setattr(familiar_bot, "FAMILIARES_PATH", fam)
    monkeypatch.setattr(familiar_bot, "PERFIL_PATH", perfil)
    monkeypatch.setattr(familiar_bot, "STATS_PATH", stats)
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.delenv("CHAT_ID", raising=False)
    yield


def _fake_update(chat_id=1, first_name="Germán", text="", voice=None):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.text = text
    update.message.voice = voice
    update.message.reply_text = AsyncMock()
    return update


def _fake_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    return ctx


# ---------------------------------------------------------------------------
# Helpers de familiares
# ---------------------------------------------------------------------------

def test_cargar_familiares_archivo_inexistente():
    assert familiar_bot.cargar_familiares() == []


def test_cargar_familiares_con_datos():
    familiar_bot.FAMILIARES_PATH.write_text(
        json.dumps([{"chat_id": 1, "nombre": "Ana"}]), encoding="utf-8"
    )
    assert familiar_bot.cargar_familiares() == [{"chat_id": 1, "nombre": "Ana"}]


def test_guardar_familiares_persiste():
    familiar_bot.guardar_familiares([{"chat_id": 7, "nombre": "Pepe"}])
    data = json.loads(familiar_bot.FAMILIARES_PATH.read_text(encoding="utf-8"))
    assert data == [{"chat_id": 7, "nombre": "Pepe"}]


def test_es_suscriptor_true():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "x"}])
    assert familiar_bot.es_suscriptor(42) is True


def test_es_suscriptor_false():
    assert familiar_bot.es_suscriptor(999) is False


def test_agregar_familiar_nuevo_devuelve_true():
    assert familiar_bot.agregar_familiar(42) is True
    assert familiar_bot.cargar_familiares() == [{"chat_id": 42, "nombre": ""}]


def test_agregar_familiar_existente_devuelve_false():
    familiar_bot.agregar_familiar(42)
    assert familiar_bot.agregar_familiar(42) is False
    assert len(familiar_bot.cargar_familiares()) == 1


def test_actualizar_nombre_familiar_existente():
    familiar_bot.agregar_familiar(42)
    familiar_bot.actualizar_nombre(42, "Germán")
    fams = familiar_bot.cargar_familiares()
    assert fams[0]["nombre"] == "Germán"


def test_actualizar_nombre_familiar_inexistente_lo_agrega():
    familiar_bot.actualizar_nombre(99, "Lao")
    fams = familiar_bot.cargar_familiares()
    assert any(f["chat_id"] == 99 and f["nombre"] == "Lao" for f in fams)


def test_nombre_registrado_devuelve_nombre():
    familiar_bot.guardar_familiares([{"chat_id": 1, "nombre": "Germán"}])
    assert familiar_bot.nombre_registrado(1) == "Germán"


def test_nombre_registrado_sin_nombre_usa_fallback():
    familiar_bot.guardar_familiares([{"chat_id": 1, "nombre": ""}])
    assert familiar_bot.nombre_registrado(1, fallback="Anónimo") == "Anónimo"


def test_nombre_registrado_no_existe_usa_fallback():
    assert familiar_bot.nombre_registrado(999, fallback="X") == "X"


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------

def test_leer_perfil_inexistente():
    assert "Sin perfil" in familiar_bot.leer_perfil()


def test_leer_perfil_con_archivo():
    familiar_bot.PERFIL_PATH.write_text("# Marta\n## Quién es\n- 83 años", encoding="utf-8")
    assert "83 años" in familiar_bot.leer_perfil()


def test_leer_seccion_existente():
    familiar_bot.PERFIL_PATH.write_text(
        "# Marta\n## Quién es\n- 83 años\n## Salud\n- presión", encoding="utf-8"
    )
    assert "83 años" in familiar_bot.leer_seccion("Quién es")
    assert "presión" not in familiar_bot.leer_seccion("Quién es")


def test_leer_seccion_inexistente():
    familiar_bot.PERFIL_PATH.write_text("# x", encoding="utf-8")
    assert "no encontrada" in familiar_bot.leer_seccion("Inexistente")


def test_actualizar_seccion_cambia_solo_la_seccion():
    familiar_bot.PERFIL_PATH.write_text(
        "## Quién es\n- viejo\n\n## Salud\n- presión", encoding="utf-8"
    )
    familiar_bot.actualizar_seccion("Quién es", "- nuevo")
    contenido = familiar_bot.PERFIL_PATH.read_text(encoding="utf-8")
    assert "nuevo" in contenido
    assert "presión" in contenido  # otra sección no se tocó


# ---------------------------------------------------------------------------
# cmd_start
# ---------------------------------------------------------------------------

def test_cmd_start_nuevo_familiar():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_start(update, _fake_context()))
    update.message.reply_text.assert_awaited_once()
    msg = update.message.reply_text.await_args.args[0]
    assert "quedaste registrado" in msg
    assert familiar_bot.es_suscriptor(42)


def test_cmd_start_familiar_existente():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_start(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "ya estabas" in msg


def test_cmd_start_avisa_de_nombre_si_no_registrado():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_start(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/nombre" in msg


def test_cmd_start_no_avisa_de_nombre_si_ya_lo_tiene():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Germán"}])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_start(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    # Aviso de "usá /nombre" no aparece
    assert "Usá /nombre" not in msg


# ---------------------------------------------------------------------------
# cmd_nombre
# ---------------------------------------------------------------------------

def test_cmd_nombre_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_nombre(update, _fake_context(args=["Germán"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_nombre_sin_args_muestra_actual():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Germán"}])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_nombre(update, _fake_context(args=[])))
    msg = update.message.reply_text.await_args.args[0]
    assert "Germán" in msg


def test_cmd_nombre_sin_args_sin_nombre_explica():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": ""}])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_nombre(update, _fake_context(args=[])))
    msg = update.message.reply_text.await_args.args[0]
    assert "Todavía no registraste" in msg


def test_cmd_nombre_actualiza():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": ""}])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_nombre(update, _fake_context(args=["Pepe", "Pérez"])))
    fams = familiar_bot.cargar_familiares()
    assert fams[0]["nombre"] == "Pepe Pérez"


# ---------------------------------------------------------------------------
# cmd_ayuda
# ---------------------------------------------------------------------------

def test_cmd_ayuda_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_ayuda(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_ayuda_suscriptor():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_ayuda(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/mensaje" in msg
    assert "/perfil" in msg


# ---------------------------------------------------------------------------
# cmd_suscriptores
# ---------------------------------------------------------------------------

def test_cmd_suscriptores_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_suscriptores(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_suscriptores_lista():
    familiar_bot.guardar_familiares([
        {"chat_id": 42, "nombre": "Germán"},
        {"chat_id": 99, "nombre": "Ana"},
    ])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_suscriptores(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Germán" in msg
    assert "Ana" in msg


def test_cmd_suscriptores_sin_nombre_muestra_placeholder():
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": ""}])
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_suscriptores(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "(sin nombre)" in msg


# ---------------------------------------------------------------------------
# cmd_perfil
# ---------------------------------------------------------------------------

def test_cmd_perfil_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_perfil(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_perfil_envia_contenido():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text("# Marta\n\nperfil corto", encoding="utf-8")
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_perfil(update, _fake_context()))
    update.message.reply_text.assert_awaited()
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg


def test_cmd_perfil_largo_se_paginan():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text("a" * 8500, encoding="utf-8")
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_perfil(update, _fake_context()))
    # 8500 / 4000 ≈ 3 mensajes
    assert update.message.reply_text.await_count >= 2


# ---------------------------------------------------------------------------
# cmd_stats
# ---------------------------------------------------------------------------

def test_cmd_stats_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_stats(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_stats_sin_archivo():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_stats(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Todavía no hay estadísticas" in msg


def test_cmd_stats_archivo_vacio():
    familiar_bot.agregar_familiar(42)
    familiar_bot.STATS_PATH.write_text("{}", encoding="utf-8")
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_stats(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Sin datos" in msg or "estadísticas" in msg.lower()


def test_cmd_stats_con_datos():
    familiar_bot.agregar_familiar(42)
    familiar_bot.STATS_PATH.write_text(json.dumps({
        "2026-05-22": {
            "mensajes": 12,
            "primer_mensaje": "08:00",
            "ultimo_mensaje": "22:00",
            "distress": {"1": 1, "2": 0, "3": 0},
            "analisis_nocturno": {"aprendizajes_nuevos": 2},
        }
    }), encoding="utf-8")
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_stats(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Actividad" in msg
    assert "12" in msg
    assert "1 alerta" in msg
    assert "aprendizaje" in msg


# ---------------------------------------------------------------------------
# cmd_aprendizajes
# ---------------------------------------------------------------------------

def test_cmd_aprendizajes_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_aprendizajes(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_aprendizajes_sin_seccion():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text("# perfil\n", encoding="utf-8")
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_aprendizajes(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "sin aprendizajes" in msg.lower()


def test_cmd_aprendizajes_con_seccion():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text(
        "# perfil\n\n## Aprendizajes\n- Le gusta la sopa\n\n## Ajustes sugeridos\n- Ser breve\n",
        encoding="utf-8",
    )
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_aprendizajes(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "sopa" in msg
    assert "Ser breve" in msg


# ---------------------------------------------------------------------------
# cmd_editar — flujo de conversación
# ---------------------------------------------------------------------------

def test_cmd_editar_no_suscriptor():
    update = _fake_update(chat_id=42)
    run(familiar_bot.cmd_editar(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "/start" in msg


def test_cmd_editar_suscriptor_muestra_lista():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cmd_editar(update, _fake_context()))
    assert estado == familiar_bot.ELIGIENDO
    msg = update.message.reply_text.await_args.args[0]
    assert "Quién es" in msg


def test_elegir_seccion_cancelar():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42, text="❌ Cancelar")
    estado = run(familiar_bot.elegir_seccion(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END


def test_elegir_seccion_invalida_pide_repetir():
    familiar_bot.agregar_familiar(42)
    update = _fake_update(chat_id=42, text="Algo random")
    estado = run(familiar_bot.elegir_seccion(update, _fake_context()))
    assert estado == familiar_bot.ELIGIENDO


def test_elegir_seccion_valida_muestra_contenido_actual():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text("## Quién es\n- 83 años", encoding="utf-8")
    update = _fake_update(chat_id=42, text="Quién es")
    ctx = _fake_context()
    estado = run(familiar_bot.elegir_seccion(update, ctx))
    assert estado == familiar_bot.RECIBIENDO
    assert ctx.user_data["seccion"] == "Quién es"


def test_recibir_contenido_actualiza_perfil():
    familiar_bot.agregar_familiar(42)
    familiar_bot.PERFIL_PATH.write_text(
        "## Quién es\n- viejo\n\n## Salud\n- presión", encoding="utf-8"
    )
    update = _fake_update(chat_id=42, text="- 84 años\n- contento")
    ctx = _fake_context()
    ctx.user_data = {"seccion": "Quién es"}
    estado = run(familiar_bot.recibir_contenido(update, ctx))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END
    contenido = familiar_bot.PERFIL_PATH.read_text(encoding="utf-8")
    assert "84 años" in contenido
    assert "presión" in contenido


def test_cancelar_corta_la_conversacion():
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cancelar(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END


# ---------------------------------------------------------------------------
# cmd_mensaje — flujo del puente
# ---------------------------------------------------------------------------

def test_cmd_mensaje_no_suscriptor():
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cmd_mensaje(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END


def test_cmd_mensaje_sin_bot_token(monkeypatch):
    familiar_bot.agregar_familiar(42)
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "")
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cmd_mensaje(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END
    msg = update.message.reply_text.await_args.args[0]
    assert "no configurado" in msg


def test_cmd_mensaje_sin_owner_adulto(monkeypatch):
    familiar_bot.agregar_familiar(42)
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: None)
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cmd_mensaje(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END
    msg = update.message.reply_text.await_args.args[0]
    assert "no abrió el bot" in msg


def test_cmd_mensaje_listo_pide_contenido(monkeypatch):
    familiar_bot.agregar_familiar(42)
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)
    update = _fake_update(chat_id=42)
    estado = run(familiar_bot.cmd_mensaje(update, _fake_context()))
    assert estado == familiar_bot.ESPERANDO_MENSAJE


# ---------------------------------------------------------------------------
# recibir_mensaje_familiar — texto
# ---------------------------------------------------------------------------

def test_recibir_mensaje_texto_envia_al_adulto(monkeypatch):
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Germán"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(return_value=mock_bot)
    bot_ctx.__aexit__ = AsyncMock(return_value=False)

    update = _fake_update(chat_id=42, text="hola mamá")
    with patch("familiar_bot.Bot", return_value=bot_ctx):
        estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END
    mock_bot.send_message.assert_awaited_once()
    args = mock_bot.send_message.await_args
    assert args.kwargs["chat_id"] == 1234
    assert "Germán" in args.kwargs["text"]
    assert "hola mamá" in args.kwargs["text"]


def test_recibir_mensaje_texto_vacio_pide_reintento(monkeypatch):
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Ana"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)
    update = _fake_update(chat_id=42, text="   ")
    estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    assert estado == familiar_bot.ESPERANDO_MENSAJE


def test_recibir_mensaje_falla_envio(monkeypatch):
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Ana"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(side_effect=Exception("boom"))
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    update = _fake_update(chat_id=42, text="hola")
    with patch("familiar_bot.Bot", return_value=bot_ctx):
        estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "error" in msg.lower()


def test_recibir_mensaje_owner_se_va_entre_medio(monkeypatch):
    """Si el owner desaparece después del cmd_mensaje (estado raro)."""
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "x"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: None)
    update = _fake_update(chat_id=42, text="hola")
    estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END


# ---------------------------------------------------------------------------
# _cargar_config / _nombre_adulto
# ---------------------------------------------------------------------------

def test_nombre_adulto_default():
    assert isinstance(familiar_bot._nombre_adulto(), str)


def test_cargar_config_sin_archivo(monkeypatch, tmp_path):
    monkeypatch.setattr(familiar_bot, "BASE_DIR", tmp_path)
    assert familiar_bot._cargar_config() == {}


def test_cargar_config_con_archivo(monkeypatch, tmp_path):
    cfg = tmp_path / "config.yml"
    cfg.write_text("nombre_adulto_mayor: Marta\nvoz_tts: es-AR\n", encoding="utf-8")
    monkeypatch.setattr(familiar_bot, "BASE_DIR", tmp_path)
    out = familiar_bot._cargar_config()
    assert out["nombre_adulto_mayor"] == "Marta"
    assert out["voz_tts"] == "es-AR"


# ---------------------------------------------------------------------------
# recibir_mensaje_familiar — voz (transcripción)
# ---------------------------------------------------------------------------

def test_recibir_mensaje_voz_sin_groq_key(monkeypatch):
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Ana"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot, "GROQ_API_KEY", "")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)
    voice = MagicMock()
    update = _fake_update(chat_id=42, voice=voice)
    estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END
    msg = update.message.reply_text.await_args.args[0]
    assert "GROQ_API_KEY" in msg


def test_recibir_mensaje_voz_falla_transcripcion(monkeypatch):
    familiar_bot.guardar_familiares([{"chat_id": 42, "nombre": "Ana"}])
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    monkeypatch.setattr(familiar_bot, "GROQ_API_KEY", "k")
    monkeypatch.setattr(familiar_bot.state_mod, "owner_chat_id", lambda: 1234)
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(side_effect=Exception("boom"))
    voice = MagicMock()
    voice_file = MagicMock()
    voice_file.download_to_drive = AsyncMock()
    voice.get_file = AsyncMock(return_value=voice_file)
    update = _fake_update(chat_id=42, voice=voice)
    with patch("familiar_bot.AsyncGroq", return_value=fake_groq):
        estado = run(familiar_bot.recibir_mensaje_familiar(update, _fake_context()))
    assert estado == familiar_bot.ESPERANDO_MENSAJE
    msg = update.message.reply_text.await_args.args[0]
    assert "transcribir" in msg
