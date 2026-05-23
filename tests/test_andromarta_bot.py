"""Tests para andromarta/bot.py — handlers y flujos del bot Andromarta."""

import asyncio
import random
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from andromarta import bot as andro_bot
from andromarta import ciclo as ciclo_mod
from andromarta import memoria as memoria_mod
from andromarta import estado as estado_mod
from andromarta import persona as persona_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", tmp_path / "memoria.json")
    monkeypatch.setattr(memoria_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ciclo_mod, "CICLO_PATH", tmp_path / "ciclo.json")
    monkeypatch.setattr(ciclo_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(estado_mod, "ESTADO_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(estado_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(persona_mod, "PERSONA_PATH", tmp_path / "persona.md")
    yield


# ---------------------------------------------------------------------------
# _validar_config
# ---------------------------------------------------------------------------

def test_validar_config_ok(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "12345")
    monkeypatch.setattr(andro_bot, "API_HASH", "abcdef")
    monkeypatch.setattr(andro_bot, "PHONE", "+5491100000000")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "aikiu_bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "gsk_key")
    andro_bot._validar_config()  # no debe lanzar


def test_validar_config_falta_api_id(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "")
    monkeypatch.setattr(andro_bot, "API_HASH", "abc")
    monkeypatch.setattr(andro_bot, "PHONE", "+54x")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "k")
    with pytest.raises(RuntimeError, match="API_ID"):
        andro_bot._validar_config()


def test_validar_config_api_id_no_es_numero(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "no-es-numero")
    monkeypatch.setattr(andro_bot, "API_HASH", "abc")
    monkeypatch.setattr(andro_bot, "PHONE", "+54x")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "k")
    with pytest.raises(RuntimeError, match="API_ID"):
        andro_bot._validar_config()


def test_validar_config_placeholder_en_hash(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "12345")
    monkeypatch.setattr(andro_bot, "API_HASH", "PEGA_TU_API_HASH")
    monkeypatch.setattr(andro_bot, "PHONE", "+54x")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "k")
    with pytest.raises(RuntimeError, match="API_HASH"):
        andro_bot._validar_config()


def test_validar_config_falta_groq(monkeypatch):
    monkeypatch.setattr(andro_bot, "API_ID_RAW", "12345")
    monkeypatch.setattr(andro_bot, "API_HASH", "abc")
    monkeypatch.setattr(andro_bot, "PHONE", "+54x")
    monkeypatch.setattr(andro_bot, "AIKIU_USERNAME", "bot")
    monkeypatch.setattr(andro_bot, "GROQ_API_KEY", "")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        andro_bot._validar_config()


# ---------------------------------------------------------------------------
# _bg — task tracking
# ---------------------------------------------------------------------------

def test_bg_agrega_task_y_se_limpia_al_terminar():
    async def correr():
        async def trabajo():
            await asyncio.sleep(0)
            return "ok"
        task = andro_bot._bg(trabajo())
        assert task in andro_bot._background_tasks
        result = await task
        assert result == "ok"
        # Después de terminar, no debe quedar referencia (done_callback)
        await asyncio.sleep(0)
        assert task not in andro_bot._background_tasks
    run(correr())


# ---------------------------------------------------------------------------
# Pausas — son no-op si RITMO_HUMANO=False, sleep si True
# ---------------------------------------------------------------------------

def test_pausa_lectura_no_op_sin_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    slept = []
    async def fake_sleep(t):
        slept.append(t)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    run(andro_bot._pausa_lectura("texto largo"))
    assert slept == []


def test_pausa_lectura_si_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", True)
    slept = []
    async def fake_sleep(t):
        slept.append(t)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(random, "uniform", lambda a, b: a)
    run(andro_bot._pausa_lectura("texto largo"))
    assert slept and slept[0] >= 1.0


def test_pausa_tipeo_no_op_sin_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    dur = run(andro_bot._pausa_tipeo("texto"))
    assert dur == 0.0


def test_pausa_tipeo_si_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", True)
    slept = []
    async def fake_sleep(t):
        slept.append(t)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(random, "uniform", lambda a, b: 0)
    dur = run(andro_bot._pausa_tipeo("hola"))
    assert dur > 0


def test_pausa_grabacion_no_op_sin_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    slept = []
    async def fake_sleep(t):
        slept.append(t)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    run(andro_bot._pausa_grabacion())
    assert slept == []


def test_pausa_grabacion_si_ritmo(monkeypatch):
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", True)
    slept = []
    async def fake_sleep(t):
        slept.append(t)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(random, "uniform", lambda a, b: 2.0)
    run(andro_bot._pausa_grabacion())
    assert slept and slept[0] == 2.0


# ---------------------------------------------------------------------------
# _enviar_texto / _enviar_voz / _enviar_respuesta
# ---------------------------------------------------------------------------

def _fake_client_y_entity():
    client = MagicMock()
    action_ctx = MagicMock()
    action_ctx.__aenter__ = AsyncMock(return_value=None)
    action_ctx.__aexit__ = AsyncMock(return_value=False)
    client.action = MagicMock(return_value=action_ctx)
    client.send_message = AsyncMock()
    client.send_file = AsyncMock()
    entity = MagicMock()
    return client, entity


def test_enviar_texto(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    run(andro_bot._enviar_texto("hola"))
    client.send_message.assert_awaited_once()
    args = client.send_message.await_args
    assert args.args[0] is entity
    assert args.args[1] == "hola"


def test_enviar_voz(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    sintetizar_calls = []
    async def fake_sintetizar(texto, salida, voz):
        sintetizar_calls.append((texto, voz))
        salida.write_bytes(b"audio")
    monkeypatch.setattr(andro_bot, "sintetizar", fake_sintetizar)
    run(andro_bot._enviar_voz("hola"))
    assert sintetizar_calls == [("hola", andro_bot.VOZ_TTS)]
    client.send_file.assert_awaited_once()


def test_enviar_respuesta_vacia_no_envia(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    run(andro_bot._enviar_respuesta("", prefiere_voz=True))
    client.send_message.assert_not_awaited()
    client.send_file.assert_not_awaited()


def test_enviar_respuesta_texto_por_random(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    # random.random > VOZ_PROB → manda texto
    monkeypatch.setattr(random, "random", lambda: 0.99)
    run(andro_bot._enviar_respuesta("hola", prefiere_voz=True))
    client.send_message.assert_awaited_once()
    client.send_file.assert_not_awaited()


def test_enviar_respuesta_voz_si_random_bajo(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 1.0)
    monkeypatch.setattr(random, "random", lambda: 0.01)
    async def fake_sintetizar(texto, salida, voz):
        salida.write_bytes(b"x")
    monkeypatch.setattr(andro_bot, "sintetizar", fake_sintetizar)
    run(andro_bot._enviar_respuesta("hola", prefiere_voz=True))
    client.send_file.assert_awaited_once()


def test_enviar_respuesta_voz_falla_cae_a_texto(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 1.0)
    monkeypatch.setattr(random, "random", lambda: 0.01)
    # sintetizar falla
    async def fake_sintetizar(texto, salida, voz):
        raise RuntimeError("tts down")
    monkeypatch.setattr(andro_bot, "sintetizar", fake_sintetizar)
    run(andro_bot._enviar_respuesta("hola", prefiere_voz=True))
    # Cayó a texto
    client.send_message.assert_awaited_once()


def test_enviar_respuesta_no_voz_si_no_prefiere(monkeypatch):
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 1.0)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    run(andro_bot._enviar_respuesta("hola", prefiere_voz=False))
    client.send_message.assert_awaited_once()
    client.send_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# _on_clara_msg — handler principal
# ---------------------------------------------------------------------------

def _fake_event(text="hola che", es_voz=False):
    event = MagicMock()
    msg = MagicMock()
    msg.text = text
    msg.voice = MagicMock() if es_voz else None
    msg.download_media = AsyncMock()
    event.message = msg
    return event


def test_on_clara_msg_ciclo_cerrado_ignora(monkeypatch):
    # Cerrar el ciclo
    ciclo_mod.guardar({"abierto": False, "turnos": 10, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 15)
    event = _fake_event(text="hola")
    run(andro_bot._on_clara_msg(event))
    client.send_message.assert_not_awaited()
    client.send_file.assert_not_awaited()


def test_on_clara_msg_sin_mensaje_no_hace_nada(monkeypatch):
    event = MagicMock()
    event.message = None
    run(andro_bot._on_clara_msg(event))  # no debe lanzar


def test_on_clara_msg_texto_genera_y_responde(monkeypatch):
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 15)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 0.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)

    async def fake_responder(**kw):
        assert kw["mensaje_de_clara"] == "hola che"
        assert kw["despedida"] is False
        return "buenas mi vida"
    monkeypatch.setattr(andro_bot, "responder", fake_responder)

    event = _fake_event(text="hola che")
    run(andro_bot._on_clara_msg(event))
    client.send_message.assert_awaited_once()
    args = client.send_message.await_args
    assert args.args[1] == "buenas mi vida"
    # Y registró turnos
    estado = ciclo_mod.cargar()
    assert estado["turnos"] == 2  # user + assistant


def test_on_clara_msg_voz_transcribe_y_responde(monkeypatch):
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 15)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 0.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)

    async def fake_transcribir(p):
        return "hola desde voz"
    monkeypatch.setattr(andro_bot, "_transcribir", fake_transcribir)

    async def fake_responder(**kw):
        assert kw["mensaje_de_clara"] == "hola desde voz"
        return "respuesta a voz"
    monkeypatch.setattr(andro_bot, "responder", fake_responder)

    event = _fake_event(es_voz=True)
    run(andro_bot._on_clara_msg(event))
    client.send_message.assert_awaited_once()


def test_on_clara_msg_error_procesando_no_rompe(monkeypatch):
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    async def fake_transcribir(p):
        raise RuntimeError("stt down")
    monkeypatch.setattr(andro_bot, "_transcribir", fake_transcribir)
    event = _fake_event(es_voz=True)
    run(andro_bot._on_clara_msg(event))  # no debe lanzar
    client.send_message.assert_not_awaited()


def test_on_clara_msg_texto_vacio_ignora(monkeypatch):
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    event = _fake_event(text="   ")
    run(andro_bot._on_clara_msg(event))
    client.send_message.assert_not_awaited()


def test_on_clara_msg_responder_falla_no_rompe(monkeypatch):
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 15)
    async def fake_responder(**kw):
        raise RuntimeError("llm down")
    monkeypatch.setattr(andro_bot, "responder", fake_responder)
    event = _fake_event(text="hola")
    run(andro_bot._on_clara_msg(event))
    client.send_message.assert_not_awaited()


def test_on_clara_msg_despedida_cierra_ciclo(monkeypatch):
    """Si el próximo turno alcanza el tope, marca despedida y cierra al final."""
    ciclo_mod.guardar({"abierto": True, "turnos": 0, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    # Max 2 turnos: el mensaje de Clara llega y la respuesta de Marta lo lleva al tope
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 2)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 0.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)

    despedidas = []
    async def fake_responder(**kw):
        despedidas.append(kw["despedida"])
        return "bueno te dejo"
    monkeypatch.setattr(andro_bot, "responder", fake_responder)

    event = _fake_event(text="último mensaje del ciclo")
    run(andro_bot._on_clara_msg(event))
    assert despedidas == [True]
    estado = ciclo_mod.cargar()
    assert estado["abierto"] is False


# ---------------------------------------------------------------------------
# _disparar_iniciativa
# ---------------------------------------------------------------------------

def test_disparar_iniciativa_sin_entity_no_hace_nada(monkeypatch):
    monkeypatch.setattr(andro_bot, "aikiu_entity", None)
    monkeypatch.setattr(andro_bot, "client", MagicMock())
    run(andro_bot._disparar_iniciativa())


def test_disparar_iniciativa_abre_ciclo_y_envia(monkeypatch):
    ciclo_mod.guardar({"abierto": False, "turnos": 15, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 0.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)

    async def fake_responder(**kw):
        assert kw["mensaje_de_clara"] is None
        return "che, ¿cómo va?"
    monkeypatch.setattr(andro_bot, "responder", fake_responder)

    run(andro_bot._disparar_iniciativa())
    estado = ciclo_mod.cargar()
    assert estado["abierto"] is True
    assert estado["turnos"] >= 1
    client.send_message.assert_awaited_once()


def test_disparar_iniciativa_falla_no_rompe(monkeypatch):
    ciclo_mod.guardar({"abierto": False, "turnos": 15, "iniciado": "x"})
    client, entity = _fake_client_y_entity()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    async def fake_responder(**kw):
        raise RuntimeError("down")
    monkeypatch.setattr(andro_bot, "responder", fake_responder)
    run(andro_bot._disparar_iniciativa())
    client.send_message.assert_not_awaited()


# ---------------------------------------------------------------------------
# _ts helper
# ---------------------------------------------------------------------------

def test_ts_formato_iso():
    assert "T" in andro_bot._ts()


# ---------------------------------------------------------------------------
# _transcribir
# ---------------------------------------------------------------------------

def test_transcribir_con_archivo(tmp_path, monkeypatch):
    ogg = tmp_path / "x.ogg"
    ogg.write_bytes(b"audio bytes")
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value="texto transcripto")
    monkeypatch.setattr(andro_bot, "groq", fake_groq)
    texto = run(andro_bot._transcribir(ogg))
    assert texto == "texto transcripto"


def test_transcribir_resultado_con_atributo_text(tmp_path, monkeypatch):
    """Algunas versiones de Groq devuelven un objeto con .text en vez de string."""
    ogg = tmp_path / "x.ogg"
    ogg.write_bytes(b"x")
    res = MagicMock()
    res.text = "texto del objeto"
    # Para que el isinstance(result, str) falle, le quitamos cualquier tipo str
    res.__class__ = type("R", (), {"text": "texto del objeto"})
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value=res)
    monkeypatch.setattr(andro_bot, "groq", fake_groq)
    texto = run(andro_bot._transcribir(ogg))
    # Cualquiera de las dos formas es aceptable: lo que importa es que devuelva un string limpio
    assert isinstance(texto, str) and "texto" in texto
