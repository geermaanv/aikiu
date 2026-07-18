"""
Tests del wizard de onboarding del bot principal (aikiu.py).

El wizard se dispara en el primer /start de un chat_id nuevo (o de uno
que tiene `perfil_completo: false` en su state). Hace 5 preguntas en
cadena (nombre, edad, ciudad, familia, gustos), persiste el progreso
incrementalmente en `instances/<chat_id>/state.json` y al final escribe
el `perfil.md` usando `configurar.generar_perfil`.

Backwards-compat: si el adulto ya tiene `perfil_completo: true`,
`cmd_start` manda un saludo simple y termina la conversación (END).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.ext import ConversationHandler

import aikiu
from core import hogar as hogar_mod


def run(coro):
    return asyncio.run(coro)


def _fake_update(chat_id=42, first_name="Juan", text="", voice=None):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.text = text
    update.message.voice = voice
    update.message.reply_text = AsyncMock()
    return update


def _fake_context():
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot_data = {}
    return ctx


@pytest.fixture(autouse=True)
def _config_neutro():
    """El template neutro tiene nombre_adulto_mayor='' — emulamos eso."""
    with patch("aikiu.CONFIG", {
        "nombre_adulto_mayor": "",
        "nombre_asistente": "Aikiu",
        "modelo_llm": "llama-3.3-70b-versatile",
    }):
        yield


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def test_normalizar_respuesta_nombre_strip():
    assert aikiu._normalizar_respuesta_onboarding("  Pedro  ", "nombre") == "Pedro"


def test_inferir_genero():
    assert aikiu._inferir_genero("Marta") == "F"
    assert aikiu._inferir_genero("Rosa") == "F"
    assert aikiu._inferir_genero("Pedro") == "M"
    assert aikiu._inferir_genero("German") == "M"   # override (termina en 'n')
    assert aikiu._inferir_genero("Juan") == "M"      # override
    assert aikiu._inferir_genero("Carmen") == "F"    # override
    assert aikiu._inferir_genero("") == "F"          # default


def test_normalizar_nombre_extrae_de_frase_conversacional():
    # El bug reportado: "hola, soy german" se guardaba entero como nombre.
    assert aikiu._normalizar_respuesta_onboarding("hola, soy german", "nombre") == "German"
    assert aikiu._normalizar_respuesta_onboarding("me llamo marta", "nombre") == "Marta"
    assert aikiu._normalizar_respuesta_onboarding("german", "nombre") == "German"
    assert aikiu._normalizar_respuesta_onboarding("soy maría josé", "nombre") == "María José"
    assert aikiu._normalizar_respuesta_onboarding("MARTA", "nombre") == "Marta"
    # Solo saludo/presentación sin nombre → vacío → el wizard re-pregunta.
    assert aikiu._normalizar_respuesta_onboarding("hola soy", "nombre") == ""


def test_normalizar_respuesta_no_se_es_vacio_en_campo_opcional():
    assert aikiu._normalizar_respuesta_onboarding("no sé", "edad") == ""
    assert aikiu._normalizar_respuesta_onboarding("no", "ciudad") == ""
    assert aikiu._normalizar_respuesta_onboarding("ninguno", "familiares") == []


def test_normalizar_respuesta_familiares_parsea_lista():
    res = aikiu._normalizar_respuesta_onboarding(
        "mi hija Laura, mi nieto Juan", "familiares"
    )
    assert res == ["mi hija Laura", "mi nieto Juan"]


def test_normalizar_respuesta_gustos_separa_por_lineas():
    res = aikiu._normalizar_respuesta_onboarding("tango\ncocinar\nplantas", "gustos")
    assert res == ["tango", "cocinar", "plantas"]


def test_normalizar_respuesta_vacio_devuelve_vacio():
    assert aikiu._normalizar_respuesta_onboarding("", "nombre") == ""


def test_onboarding_pendiente_si_no_hay_flag():
    assert aikiu._onboarding_pendiente({}) is True
    assert aikiu._onboarding_pendiente({"perfil_completo": False}) is True


def test_onboarding_completo_si_flag_true():
    assert aikiu._onboarding_pendiente({"perfil_completo": True}) is False


def test_proximo_paso_arranca_en_nombre():
    assert aikiu._proximo_paso_onboarding({}) == aikiu.OB_NOMBRE


def test_proximo_paso_avanza_segun_progreso():
    estado = {"onboarding_progress": {"nombre": "Pedro"}}
    assert aikiu._proximo_paso_onboarding(estado) == aikiu.OB_EDAD


def test_proximo_paso_familia_si_nombre_edad_ciudad_listos():
    estado = {"onboarding_progress": {"nombre": "Pedro", "edad": "78", "ciudad": "Rosario"}}
    assert aikiu._proximo_paso_onboarding(estado) == aikiu.OB_FAMILIA


# ---------------------------------------------------------------------------
# cmd_start arranca el wizard cuando el hogar está sin onboardear
# ---------------------------------------------------------------------------

def test_cmd_start_hogar_nuevo_arranca_wizard():
    update = _fake_update(chat_id=999, first_name="Juan")
    ctx = _fake_context()
    estado = run(aikiu.cmd_start(update, ctx))
    assert estado == aikiu.OB_NOMBRE
    ctx.bot.send_message.assert_awaited_once()
    msg = ctx.bot.send_message.await_args.kwargs.get("text", "")
    assert "1/5" in msg
    assert "Cómo te llamás" in msg
    assert "Juan" in msg  # incluye el first_name de Telegram en el saludo


def test_cmd_start_hogar_con_perfil_completo_no_arranca_wizard():
    hogar_mod.crear_hogar(42)
    estado_inicial = hogar_mod.leer_state(42) or {"owner_chat_id": 42}
    estado_inicial["perfil_completo"] = True
    estado_inicial["nombre_adulto_mayor"] = "Marta"
    hogar_mod.escribir_state(42, estado_inicial)

    update = _fake_update(chat_id=42, first_name="Marta")
    ctx = _fake_context()
    estado = run(aikiu.cmd_start(update, ctx))
    assert estado == ConversationHandler.END
    ctx.bot.send_message.assert_awaited_once()
    msg = ctx.bot.send_message.await_args.kwargs.get("text", "")
    assert "Marta" in msg
    assert "Aikiu" in msg
    assert "1/5" not in msg  # NO arranca el wizard


def test_cmd_start_reanuda_desde_paso_pendiente():
    """Si un adulto se cortó a mitad del wizard, /start retoma desde donde quedó."""
    hogar_mod.crear_hogar(42, nombre="Juan")
    estado = hogar_mod.leer_state(42)
    estado["onboarding_progress"] = {"nombre": "Pedro"}
    hogar_mod.escribir_state(42, estado)

    update = _fake_update(chat_id=42, first_name="Pedro")
    ctx = _fake_context()
    estado_conv = run(aikiu.cmd_start(update, ctx))
    assert estado_conv == aikiu.OB_EDAD
    msg = ctx.bot.send_message.await_args.kwargs.get("text", "")
    assert "2/5" in msg


# ---------------------------------------------------------------------------
# Flujo completo del wizard
# ---------------------------------------------------------------------------

def test_wizard_completo_persiste_progreso_y_genera_perfil():
    chat_id = 4242

    # /start → arranca el wizard
    ctx = _fake_context()
    estado = run(aikiu.cmd_start(_fake_update(chat_id=chat_id, first_name="Pedro"), ctx))
    assert estado == aikiu.OB_NOMBRE

    # 1/5 nombre
    estado = run(aikiu.ob_nombre(_fake_update(chat_id=chat_id, text="Pedro"), ctx))
    assert estado == aikiu.OB_EDAD
    assert hogar_mod.leer_state(chat_id)["onboarding_progress"]["nombre"] == "Pedro"

    # 2/5 edad
    estado = run(aikiu.ob_edad(_fake_update(chat_id=chat_id, text="78"), ctx))
    assert estado == aikiu.OB_CIUDAD
    assert hogar_mod.leer_state(chat_id)["onboarding_progress"]["edad"] == "78"

    # 3/5 ciudad
    estado = run(aikiu.ob_ciudad(_fake_update(chat_id=chat_id, text="Rosario"), ctx))
    assert estado == aikiu.OB_FAMILIA

    # 4/5 familia
    estado = run(aikiu.ob_familia(_fake_update(chat_id=chat_id, text="mi hijo Juan, mi nieta Cata"), ctx))
    assert estado == aikiu.OB_GUSTOS
    assert hogar_mod.leer_state(chat_id)["onboarding_progress"]["familiares"] == [
        "mi hijo Juan", "mi nieta Cata"
    ]

    # 5/5 gustos → dispara persistencia final
    estado = run(aikiu.ob_gustos(_fake_update(chat_id=chat_id, text="tango, cocinar"), ctx))
    assert estado == ConversationHandler.END

    # Perfil generado
    perfil = hogar_mod.perfil_path(chat_id).read_text(encoding="utf-8")
    assert "# Perfil de Pedro" in perfil
    assert "Pedro, 78 años, vive en Rosario" in perfil
    assert "mi hijo Juan" in perfil
    assert "tango" in perfil

    # State marcado como completo + overrides puestos
    final = hogar_mod.leer_state(chat_id)
    assert final["perfil_completo"] is True
    assert final["nombre_adulto_mayor"] == "Pedro"
    assert final["ciudad"] == "Rosario"


def test_wizard_nombre_vacio_pide_de_nuevo():
    """Sin nombre no se puede arrancar — re-pregunta hasta que haya nombre."""
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=55, first_name="X"), ctx))
    estado = run(aikiu.ob_nombre(_fake_update(chat_id=55, text=""), ctx))
    assert estado == aikiu.OB_NOMBRE  # no avanzó


def test_wizard_no_se_en_edad_marca_vacio_y_avanza():
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=56, first_name="X"), ctx))
    run(aikiu.ob_nombre(_fake_update(chat_id=56, text="Ana"), ctx))
    estado = run(aikiu.ob_edad(_fake_update(chat_id=56, text="no sé"), ctx))
    assert estado == aikiu.OB_CIUDAD
    assert hogar_mod.leer_state(56)["onboarding_progress"]["edad"] == ""


# ---------------------------------------------------------------------------
# Saltar y cancelar
# ---------------------------------------------------------------------------

def test_cmd_saltar_nombre_no_permitido():
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=60, first_name="X"), ctx))
    estado = run(aikiu.cmd_saltar(_fake_update(chat_id=60), ctx))
    assert estado == aikiu.OB_NOMBRE  # no avanza, sigue en nombre


def test_cmd_saltar_edad_pasa_a_ciudad():
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=61, first_name="X"), ctx))
    run(aikiu.ob_nombre(_fake_update(chat_id=61, text="Ana"), ctx))
    estado = run(aikiu.cmd_saltar(_fake_update(chat_id=61), ctx))
    assert estado == aikiu.OB_CIUDAD
    assert hogar_mod.leer_state(61)["onboarding_progress"]["edad"] == ""


def test_cmd_saltar_ultima_pregunta_finaliza_wizard():
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=62, first_name="X"), ctx))
    run(aikiu.ob_nombre(_fake_update(chat_id=62, text="Ana"), ctx))
    run(aikiu.ob_edad(_fake_update(chat_id=62, text="80"), ctx))
    run(aikiu.ob_ciudad(_fake_update(chat_id=62, text="Tigre"), ctx))
    run(aikiu.ob_familia(_fake_update(chat_id=62, text="mi sobrina"), ctx))
    # /saltar en la última pregunta finaliza
    estado = run(aikiu.cmd_saltar(_fake_update(chat_id=62), ctx))
    assert estado == ConversationHandler.END
    assert hogar_mod.leer_state(62)["perfil_completo"] is True


def test_cmd_cancelar_aborta_sin_marcar_completo():
    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=63, first_name="X"), ctx))
    run(aikiu.ob_nombre(_fake_update(chat_id=63, text="Ana"), ctx))
    estado = run(aikiu.cmd_cancelar_onboarding(_fake_update(chat_id=63), ctx))
    assert estado == ConversationHandler.END
    # No marcó perfil_completo
    final = hogar_mod.leer_state(63)
    assert "perfil_completo" not in final or final["perfil_completo"] is False
    # El progreso sigue persistido por si vuelve a /start después
    assert final["onboarding_progress"]["nombre"] == "Ana"


# ---------------------------------------------------------------------------
# Wizard por voz
# ---------------------------------------------------------------------------

def test_wizard_acepta_voz_transcrita(monkeypatch):
    """Si el adulto contesta por voz, el texto sale de transcribir()."""
    async def fake_transcribir(_):
        return "  Pedro  "
    monkeypatch.setattr(aikiu, "transcribir", fake_transcribir)

    voice_msg = MagicMock()
    voice_file = MagicMock()
    voice_file.download_to_drive = AsyncMock()
    voice_msg.get_file = AsyncMock(return_value=voice_file)

    ctx = _fake_context()
    run(aikiu.cmd_start(_fake_update(chat_id=70, first_name="X"), ctx))
    update_voz = _fake_update(chat_id=70, text="", voice=voice_msg)
    estado = run(aikiu.ob_nombre(update_voz, ctx))
    assert estado == aikiu.OB_EDAD
    assert hogar_mod.leer_state(70)["onboarding_progress"]["nombre"] == "Pedro"


def test_config_hogar_promueve_genero_y_medio_del_state(monkeypatch):
    """Bug real (18/07): `genero` se guardaba M en el state del hogar pero
    `_config_hogar` no lo promovía, así que `_genero_de` leía el default
    global (F) y trataba a un hombre en femenino. Toda clave overrideable
    por hogar tiene que estar en la lista de promoción."""
    monkeypatch.setattr(aikiu, "_state_hogar", lambda cid: {
        "nombre_adulto_mayor": "Nico", "genero": "M", "medio": "voz",
    })
    vista = aikiu._config_hogar(999)
    assert vista["genero"] == "M"
    assert vista["medio"] == "voz"
    assert aikiu._genero_de(999) == "M"
    assert aikiu._medio_de(999) == "voz"
