"""
Tests extra para aikiu.py — cubre handlers, generación, registros y main flow
que no estaban testeados en los suites previos.
"""

import asyncio
import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aikiu
from core import state as state_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.delenv("CHAT_ID", raising=False)
    yield


def _mock_groq(respuesta: str, raw=False):
    choice = MagicMock()
    choice.message.content = respuesta
    completion = MagicMock()
    completion.choices = [choice]
    completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    groq = MagicMock()
    groq.chat.completions.create = AsyncMock(return_value=completion)
    return groq


# ---------------------------------------------------------------------------
# transcribir
# ---------------------------------------------------------------------------

def test_transcribir_audio_funciona(tmp_path):
    ogg = tmp_path / "x.ogg"
    ogg.write_bytes(b"audio data")
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value="hola")
    with patch("aikiu.groq", fake_groq):
        texto = run(aikiu.transcribir(ogg))
    assert texto == "hola"


def test_transcribir_archivo_inexistente(tmp_path):
    ogg = tmp_path / "no.ogg"
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value="x")
    # Falla al abrir el archivo
    with patch("aikiu.groq", fake_groq), pytest.raises(FileNotFoundError):
        run(aikiu.transcribir(ogg))


def test_transcribir_resultado_objeto_con_text(tmp_path):
    ogg = tmp_path / "x.ogg"
    ogg.write_bytes(b"x")
    # Objeto que NO es str pero tiene .text
    class Resp:
        text = "transcripto"
    fake_groq = MagicMock()
    fake_groq.audio.transcriptions.create = AsyncMock(return_value=Resp())
    with patch("aikiu.groq", fake_groq):
        texto = run(aikiu.transcribir(ogg))
    assert texto == "transcripto"


# ---------------------------------------------------------------------------
# generar_respuesta
# ---------------------------------------------------------------------------

def test_generar_respuesta_basica():
    fake_groq = _mock_groq("Hola Marta")
    cfg = {
        "nombre_asistente": "Aikiu",
        "nombre_adulto_mayor": "Marta",
        "_perfil": "",
        "modelo_llm": "llama-3.3-70b-versatile",
    }
    with patch("aikiu.CONFIG", cfg), patch("aikiu.groq", fake_groq):
        out = run(aikiu.generar_respuesta("hola", []))
    assert out == "Hola Marta"


def test_generar_respuesta_inyecta_datos_externos_si_pre_route_devuelve_algo():
    fake_groq = _mock_groq("Hace 18 grados")
    cfg = {"nombre_asistente": "Aikiu", "nombre_adulto_mayor": "Marta", "_perfil": "",
           "modelo_llm": "m", "ciudad": "Buenos Aires"}
    with patch("aikiu.CONFIG", cfg), patch("aikiu.groq", fake_groq), \
         patch("aikiu.consultar_clima", new=AsyncMock(return_value="Temperatura 18°C")):
        run(aikiu.generar_respuesta("¿qué temperatura hace?", []))
    msgs = fake_groq.chat.completions.create.await_args.kwargs["messages"]
    # Debe haber un system con los datos externos
    contenidos = [m["content"] for m in msgs if m["role"] == "system"]
    assert any("Temperatura 18" in c for c in contenidos)


def test_generar_respuesta_inyecta_temas_a_evitar(tmp_path, monkeypatch):
    """Si _temas_a_evitar devuelve algo, lo mete como instrucción."""
    fake_groq = _mock_groq("ok")
    cfg = {"nombre_asistente": "Aikiu", "nombre_adulto_mayor": "Marta", "_perfil": "",
           "modelo_llm": "m"}
    with patch("aikiu.CONFIG", cfg), patch("aikiu.groq", fake_groq), \
         patch("aikiu._temas_a_evitar", return_value=["tango", "política"]):
        run(aikiu.generar_respuesta("hola", []))
    msgs = fake_groq.chat.completions.create.await_args.kwargs["messages"]
    todos = " ".join(m["content"] for m in msgs)
    assert "tango" in todos and "política" in todos


def test_generar_respuesta_inyecta_temas_preferidos():
    fake_groq = _mock_groq("ok")
    cfg = {"nombre_asistente": "Aikiu", "nombre_adulto_mayor": "Marta", "_perfil": "",
           "modelo_llm": "m"}
    with patch("aikiu.CONFIG", cfg), patch("aikiu.groq", fake_groq), \
         patch("aikiu._temas_a_evitar", return_value=[]), \
         patch("aikiu._temas_preferidos", return_value=["cocina", "plantas", "nietos"]):
        run(aikiu.generar_respuesta("hola", []))
    msgs = fake_groq.chat.completions.create.await_args.kwargs["messages"]
    contenidos = " ".join(m["content"] for m in msgs)
    assert "cocina" in contenidos


def test_generar_respuesta_filtra_preferidos_que_aparecen_en_evitar():
    fake_groq = _mock_groq("ok")
    cfg = {"nombre_asistente": "Aikiu", "nombre_adulto_mayor": "Marta", "_perfil": "",
           "modelo_llm": "m"}
    with patch("aikiu.CONFIG", cfg), patch("aikiu.groq", fake_groq), \
         patch("aikiu._temas_a_evitar", return_value=["tango"]), \
         patch("aikiu._temas_preferidos", return_value=["tango", "cocina"]):
        run(aikiu.generar_respuesta("hola", []))
    msgs = fake_groq.chat.completions.create.await_args.kwargs["messages"]
    preferidos_msgs = [m["content"] for m in msgs if "alto engagement" in m.get("content", "")]
    assert preferidos_msgs
    # Tango fue excluido
    assert "tango" not in preferidos_msgs[0]
    assert "cocina" in preferidos_msgs[0]


# ---------------------------------------------------------------------------
# registrar_log
# ---------------------------------------------------------------------------

def test_registrar_log_crea_archivo_y_encabezado(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"})
    aikiu.registrar_log("hola", "buenas")
    files = list((tmp_path / "logs").glob("*.md"))
    assert files
    contenido = files[0].read_text(encoding="utf-8")
    assert "Conversaciones" in contenido
    assert "Marta: hola" in contenido
    assert "Aikiu: buenas" in contenido


def test_registrar_log_appende_si_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"})
    aikiu.registrar_log("uno", "uno-r")
    aikiu.registrar_log("dos", "dos-r")
    files = list((tmp_path / "logs").glob("*.md"))
    contenido = files[0].read_text(encoding="utf-8")
    assert "Marta: uno" in contenido
    assert "Marta: dos" in contenido


# ---------------------------------------------------------------------------
# chat_id_autorizado + _owner_chat_id_o_warn
# ---------------------------------------------------------------------------

def test_chat_id_autorizado_true():
    # En multi-tenant, todo chat_id puede operar (cada uno tiene su hogar).
    state_mod.registrar_owner(42)
    assert aikiu.chat_id_autorizado(42) is True


def test_chat_id_autorizado_acepta_cualquier_chat_id_en_multi_tenant():
    """Antes era TOFU global y rechazaba el segundo chat. Ahora cada chat
    crea su propio hogar, así que siempre se autoriza."""
    state_mod.registrar_owner(42)
    assert aikiu.chat_id_autorizado(99) is True


def test_owner_chat_id_o_warn_sin_owner():
    assert aikiu._owner_chat_id_o_warn() is None


def test_owner_chat_id_o_warn_con_owner():
    state_mod.registrar_owner(42)
    assert aikiu._owner_chat_id_o_warn() == 42


# ---------------------------------------------------------------------------
# cmd_start
# ---------------------------------------------------------------------------

def _fake_update(chat_id=42, first_name="Marta"):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _fake_context():
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_chat_action = AsyncMock()
    ctx.bot.send_voice = AsyncMock()
    ctx.bot_data = {}
    return ctx


def test_cmd_start_crea_hogar_y_responde():
    """En multi-tenant, cada /start crea un hogar para el chat_id que lo manda."""
    from core import hogar as hogar_mod
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"}):
        run(aikiu.cmd_start(update, ctx))
    assert hogar_mod.existe_hogar(42)
    ctx.bot.send_message.assert_awaited_once()


def test_cmd_start_segundo_chat_id_tambien_crea_su_hogar():
    """Un segundo chat_id distinto no se rechaza: crea su propio hogar."""
    from core import hogar as hogar_mod
    update1 = _fake_update(chat_id=42)
    update2 = _fake_update(chat_id=999)
    ctx1 = _fake_context()
    ctx2 = _fake_context()
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"}):
        run(aikiu.cmd_start(update1, ctx1))
        run(aikiu.cmd_start(update2, ctx2))
    assert hogar_mod.existe_hogar(42)
    assert hogar_mod.existe_hogar(999)
    ctx1.bot.send_message.assert_awaited_once()
    ctx2.bot.send_message.assert_awaited_once()


def test_cmd_invitar_genera_codigo_y_responde():
    """`/invitar` crea un código de 6 caracteres y lo envía al adulto."""
    from core import hogar as hogar_mod
    from core import invites as invites_mod
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    ctx.args = []
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"}):
        run(aikiu.cmd_invitar(update, ctx))
    assert hogar_mod.existe_hogar(42)
    ctx.bot.send_message.assert_awaited_once()
    msg = ctx.bot.send_message.await_args.kwargs.get("text", ctx.bot.send_message.await_args.args[1] if len(ctx.bot.send_message.await_args.args) > 1 else "")
    # El mensaje contiene un código alfanumérico de 6 caracteres del alfabeto válido
    import re
    m = re.search(r"\b([A-Z2-9]{6})\b", msg)
    assert m is not None, f"No encontré un código en el mensaje: {msg}"
    codigo = m.group(1)
    # El código existe en el storage y apunta a 42
    assert invites_mod.consumir(codigo) == 42


def test_cmd_invitar_falla_si_storage_revienta(monkeypatch):
    """Si invites.generar_codigo falla, avisa al usuario y no rompe."""
    from core import invites as invites_mod
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    ctx.args = []
    monkeypatch.setattr(invites_mod, "generar_codigo", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"}):
        run(aikiu.cmd_invitar(update, ctx))
    ctx.bot.send_message.assert_awaited_once()
    msg = ctx.bot.send_message.await_args.kwargs.get("text", "")
    assert "no pude" in msg.lower() or "intent" in msg.lower()


def test_cmd_start_hogar_existente_responde():
    from core import hogar as hogar_mod
    hogar_mod.crear_hogar(42)
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu"}):
        run(aikiu.cmd_start(update, ctx))
    ctx.bot.send_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------

def test_handle_message_chat_id_nuevo_se_da_de_alta_y_responde(monkeypatch):
    """En multi-tenant, un chat_id nuevo se da de alta automáticamente y
    se procesa el mensaje. Antes era 'rechazado'."""
    from core import hogar as hogar_mod
    update = _fake_update(chat_id=999)
    update.message.voice = None
    update.message.text = "hola"
    ctx = _fake_context()
    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m"})
    monkeypatch.setattr(aikiu, "generar_respuesta",
                        AsyncMock(return_value="ok\nDISTRESS_LEVEL: 0"))
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    run(aikiu.handle_message(update, ctx))
    assert hogar_mod.existe_hogar(999)
    ctx.bot.send_message.assert_awaited_once()


def test_handle_message_texto_responde(monkeypatch):
    state_mod.registrar_owner(42)
    update = _fake_update(chat_id=42)
    update.message.voice = None
    update.message.text = "hola Aikiu"
    ctx = _fake_context()
    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m"})
    monkeypatch.setattr(aikiu, "generar_respuesta",
                        AsyncMock(return_value="Hola Marta\nDISTRESS_LEVEL: 0"))
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    run(aikiu.handle_message(update, ctx))
    ctx.bot.send_message.assert_awaited_once()
    args = ctx.bot.send_message.await_args
    assert args.kwargs["chat_id"] == 42
    assert "Hola Marta" in args.kwargs["text"]
    assert "DISTRESS_LEVEL" not in args.kwargs["text"]


def test_handle_message_voz_responde_voz(monkeypatch):
    state_mod.registrar_owner(42)
    voice = MagicMock()
    voice_file = MagicMock()
    voice_file.download_to_drive = AsyncMock()
    voice.get_file = AsyncMock(return_value=voice_file)
    update = _fake_update(chat_id=42)
    update.message.voice = voice
    update.message.text = ""
    ctx = _fake_context()
    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m", "medio": "voz"})
    monkeypatch.setattr(aikiu, "transcribir", AsyncMock(return_value="hola en voz"))
    monkeypatch.setattr(aikiu, "generar_respuesta",
                        AsyncMock(return_value="Buenas Marta\nDISTRESS_LEVEL: 0"))
    monkeypatch.setattr(aikiu, "responder_con_voz", AsyncMock())
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    run(aikiu.handle_message(update, ctx))
    aikiu.responder_con_voz.assert_awaited_once()


def test_handle_message_voz_vacia_pide_repetir(monkeypatch):
    state_mod.registrar_owner(42)
    voice = MagicMock()
    voice_file = MagicMock()
    voice_file.download_to_drive = AsyncMock()
    voice.get_file = AsyncMock(return_value=voice_file)
    update = _fake_update(chat_id=42)
    update.message.voice = voice
    update.message.text = ""
    ctx = _fake_context()
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m", "voz_tts": "es-AR"})
    monkeypatch.setattr(aikiu, "transcribir", AsyncMock(return_value=""))
    monkeypatch.setattr(aikiu, "responder_con_voz", AsyncMock())
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    run(aikiu.handle_message(update, ctx))
    # Pidió repetir vía voz
    aikiu.responder_con_voz.assert_awaited_once()


def test_handle_message_distress_envia_alerta(monkeypatch):
    """Si DISTRESS_LEVEL >= 1 y hay family_bot, dispara notify_family."""
    state_mod.registrar_owner(42)
    update = _fake_update(chat_id=42)
    update.message.voice = None
    update.message.text = "me siento sola"
    ctx = _fake_context()
    family_bot = MagicMock()
    ctx.bot_data = {"family_bot": family_bot}
    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m"})
    monkeypatch.setattr(aikiu, "generar_respuesta",
                        AsyncMock(return_value="Entiendo Marta\nDISTRESS_LEVEL: 1"))
    notif_mock = AsyncMock()
    monkeypatch.setattr(aikiu, "notify_family", notif_mock)
    monkeypatch.setattr(aikiu, "should_send_alert", lambda *a, **k: True)
    monkeypatch.setattr(aikiu, "record_alert_sent", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    captured = []
    def captura(c):
        captured.append(c)
        return MagicMock()
    monkeypatch.setattr(aikiu, "create_background_task", captura)
    run(aikiu.handle_message(update, ctx))
    # notify_family fue planificado como background task
    for c in captured:
        try:
            run(c)
        except Exception:
            pass
    notif_mock.assert_called_once()


def test_handle_message_distress_sin_family_bot_no_explota(monkeypatch):
    state_mod.registrar_owner(42)
    update = _fake_update(chat_id=42)
    update.message.voice = None
    update.message.text = "me siento sola"
    ctx = _fake_context()
    ctx.bot_data = {}  # sin family_bot
    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "_perfil": "", "modelo_llm": "m"})
    monkeypatch.setattr(aikiu, "generar_respuesta",
                        AsyncMock(return_value="x\nDISTRESS_LEVEL: 1"))
    monkeypatch.setattr(aikiu, "should_send_alert", lambda *a, **k: True)
    monkeypatch.setattr(aikiu, "record_alert_sent", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    run(aikiu.handle_message(update, ctx))  # no debe lanzar


# ---------------------------------------------------------------------------
# responder_con_voz
# ---------------------------------------------------------------------------

def test_responder_con_voz_invoca_sintetizar(monkeypatch):
    ctx = _fake_context()
    async def fake_sintetizar(texto, salida, voz):
        salida.write_bytes(b"audio")
    monkeypatch.setattr(aikiu, "sintetizar", fake_sintetizar)
    monkeypatch.setattr(aikiu, "CONFIG", {"voz_tts": "es-AR-X"})
    run(aikiu.responder_con_voz(ctx, 42, "hola"))
    ctx.bot.send_voice.assert_awaited_once()


# ---------------------------------------------------------------------------
# enviar_mensaje_voz
# ---------------------------------------------------------------------------

def test_enviar_mensaje_voz_con_owner(monkeypatch):
    state_mod.registrar_owner(42)
    app = MagicMock()
    app.bot.send_voice = AsyncMock()
    async def fake_sintetizar(texto, salida, voz):
        salida.write_bytes(b"x")
    monkeypatch.setattr(aikiu, "sintetizar", fake_sintetizar)
    monkeypatch.setattr(aikiu, "CONFIG", {"voz_tts": "es-AR", "medio": "voz"})
    run(aikiu.enviar_mensaje_voz(app, "feliz cumpleaños"))
    app.bot.send_voice.assert_awaited_once()


def test_enviar_mensaje_voz_sin_owner_no_envia():
    app = MagicMock()
    app.bot.send_voice = AsyncMock()
    run(aikiu.enviar_mensaje_voz(app, "texto"))
    app.bot.send_voice.assert_not_awaited()


# ---------------------------------------------------------------------------
# _filtrar_instrucciones_medicas
# ---------------------------------------------------------------------------

def test_filtrar_instrucciones_medicas_remueve_indagaciones():
    instrucciones = [
        "- Preguntale por el dolor de rodilla",
        "- Saludá con más cariño",
        "- Indagá sobre los síntomas de presión",
    ]
    filtradas = aikiu._filtrar_instrucciones_medicas(instrucciones)
    assert len(filtradas) == 1
    assert "cariño" in filtradas[0]


def test_filtrar_instrucciones_medicas_sin_indagaciones():
    instrucciones = ["- Ser más breve", "- Hablar de plantas"]
    assert aikiu._filtrar_instrucciones_medicas(instrucciones) == instrucciones


def test_filtrar_instrucciones_medicas_lista_vacia():
    assert aikiu._filtrar_instrucciones_medicas([]) == []


# ---------------------------------------------------------------------------
# _ajustes_a_instrucciones
# ---------------------------------------------------------------------------

def test_ajustes_a_instrucciones_vacio():
    """Sin ajustes, devuelve [] sin llamar al LLM."""
    fake_groq = _mock_groq("no debería usarse")
    with patch("aikiu.groq", fake_groq):
        assert run(aikiu._ajustes_a_instrucciones([], "Aikiu")) == []
    fake_groq.chat.completions.create.assert_not_awaited()


def test_ajustes_a_instrucciones_convierte():
    fake_groq = _mock_groq("- No saludes siempre igual\n- Evitá tutearla")
    with patch("aikiu.groq", fake_groq), \
         patch("aikiu.CONFIG", {"modelo_llm": "m"}):
        out = run(aikiu._ajustes_a_instrucciones(
            ["A veces saluda de la misma forma", "Tutea de más"], "Aikiu"
        ))
    assert "No saludes" in out[0]
    assert len(out) == 2


def test_ajustes_a_instrucciones_falla_llm_devuelve_originales():
    fake_groq = MagicMock()
    fake_groq.chat.completions.create = AsyncMock(side_effect=Exception("down"))
    with patch("aikiu.groq", fake_groq), patch("aikiu.CONFIG", {"modelo_llm": "m"}):
        out = run(aikiu._ajustes_a_instrucciones(["a", "b"], "Aikiu"))
    assert out == ["a", "b"]


def test_ajustes_a_instrucciones_llm_sin_guiones_devuelve_originales():
    fake_groq = _mock_groq("texto sin guiones")
    with patch("aikiu.groq", fake_groq), patch("aikiu.CONFIG", {"modelo_llm": "m"}):
        out = run(aikiu._ajustes_a_instrucciones(["a"], "Aikiu"))
    assert out == ["a"]


# ---------------------------------------------------------------------------
# _alertar_sintomas_persistentes
# ---------------------------------------------------------------------------

def test_alertar_sintomas_persistentes_sin_ayer(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    # No hay log de ayer
    app = MagicMock()
    app.bot_data = {}
    run(aikiu._alertar_sintomas_persistentes(app, "dolor de rodilla"))
    # No debe fallar


def test_alertar_sintomas_persistentes_sin_sintomas_comunes(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (logs / f"{ayer}.md").write_text("hablamos de plantas", encoding="utf-8")
    monkeypatch.setattr(aikiu, "LOGS_DIR", logs)
    app = MagicMock()
    app.bot_data = {}
    run(aikiu._alertar_sintomas_persistentes(app, "fui al cine"))


def test_alertar_sintomas_persistentes_con_persistencia(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (logs / f"{ayer}.md").write_text("me duele la rodilla", encoding="utf-8")
    monkeypatch.setattr(aikiu, "LOGS_DIR", logs)
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "Marta"})
    monkeypatch.setattr(aikiu, "FAMILIARES_PATH" if hasattr(aikiu, "FAMILIARES_PATH") else "X",
                        tmp_path, raising=False)
    app = MagicMock()
    family_bot = MagicMock()
    family_bot.send_message = AsyncMock()
    app.bot_data = {"family_bot": family_bot}
    with patch("core.alerts.cargar_suscriptores", return_value=[123, 456]):
        run(aikiu._alertar_sintomas_persistentes(app, "hoy también me duele la rodilla"))
    assert family_bot.send_message.await_count == 2


def test_alertar_sintomas_persistentes_sin_family_bot_no_envia(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (logs / f"{ayer}.md").write_text("me duele la cabeza", encoding="utf-8")
    monkeypatch.setattr(aikiu, "LOGS_DIR", logs)
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "Marta"})
    app = MagicMock()
    app.bot_data = {}
    run(aikiu._alertar_sintomas_persistentes(app, "hoy me duele la cabeza"))


def test_alertar_sintomas_persistentes_app_none(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    ayer = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    (logs / f"{ayer}.md").write_text("me duele la cabeza", encoding="utf-8")
    monkeypatch.setattr(aikiu, "LOGS_DIR", logs)
    monkeypatch.setattr(aikiu, "CONFIG", {"nombre_adulto_mayor": "Marta"})
    run(aikiu._alertar_sintomas_persistentes(None, "hoy me duele la cabeza"))


# ---------------------------------------------------------------------------
# _calcular_ranking_temas
# ---------------------------------------------------------------------------

def test_calcular_ranking_sin_datos(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", tmp_path / "no.json")
    assert aikiu._calcular_ranking_temas() == []


def test_calcular_ranking_con_datos(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    ahora = datetime.now()
    rp.write_text(json.dumps([
        {"tema": "cocina",  "receptividad": "alta",  "palabras_usuario": 10, "ts": ahora.isoformat()},
        {"tema": "cocina",  "receptividad": "alta",  "palabras_usuario": 8,  "ts": ahora.isoformat()},
        {"tema": "tango",   "receptividad": "baja",  "palabras_usuario": 2,  "ts": ahora.isoformat()},
        {"tema": "plantas", "receptividad": "neutra","palabras_usuario": 5,  "ts": ahora.isoformat()},
    ]), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    monkeypatch.setattr(aikiu, "_palabras_en_aprendizajes", lambda *a, **k: set())
    ranking = aikiu._calcular_ranking_temas()
    assert ranking[0] == "cocina"  # mejor score


def test_calcular_ranking_ignora_viejos(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    viejo = (datetime.now() - timedelta(days=10)).isoformat()
    rp.write_text(json.dumps([
        {"tema": "x", "receptividad": "alta", "palabras_usuario": 10, "ts": viejo},
    ]), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    monkeypatch.setattr(aikiu, "_palabras_en_aprendizajes", lambda *a, **k: set())
    assert aikiu._calcular_ranking_temas() == []


def test_calcular_ranking_ts_invalido_se_ignora(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    rp.write_text(json.dumps([
        {"tema": "x", "receptividad": "alta", "palabras_usuario": 5, "ts": "no-fecha"},
        {"tema": "y", "receptividad": "alta", "palabras_usuario": 5, "ts": datetime.now().isoformat()},
    ]), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    monkeypatch.setattr(aikiu, "_palabras_en_aprendizajes", lambda *a, **k: set())
    ranking = aikiu._calcular_ranking_temas()
    assert ranking == ["y"]


# ---------------------------------------------------------------------------
# _palabras_en_aprendizajes
# ---------------------------------------------------------------------------

def test_palabras_en_aprendizajes_lee_perfil(tmp_path, monkeypatch):
    perfil = tmp_path / "perfil.md"
    perfil.write_text("# X\n\n## Aprendizajes\n- Le encantan las plantas y la cocina\n", encoding="utf-8")
    monkeypatch.setattr(aikiu, "PERFIL_PATH", perfil)
    palabras = aikiu._palabras_en_aprendizajes()
    assert "plantas" in palabras
    assert "cocina" in palabras


def test_palabras_en_aprendizajes_sin_perfil_devuelve_set_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "PERFIL_PATH", tmp_path / "no.md")
    assert aikiu._palabras_en_aprendizajes() == set()


# ---------------------------------------------------------------------------
# _temas_a_evitar — engagement bajo (2+ días)
# ---------------------------------------------------------------------------

def test_temas_evitar_por_engagement_bajo(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    # tema 'aburrido' aparece 2 días con avg < 3 palabras
    ahora = datetime.now()
    entradas = [
        {"tema": "aburrido", "receptividad": "neutra", "palabras_usuario": 1, "ts": ahora.isoformat()},
        {"tema": "aburrido", "receptividad": "neutra", "palabras_usuario": 2, "ts": (ahora - timedelta(days=2)).isoformat()},
    ]
    rp.write_text(json.dumps(entradas), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    evitar = aikiu._temas_a_evitar()
    assert "aburrido" in evitar


def test_temas_evitar_engagement_alto_no_se_excluye(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    ahora = datetime.now()
    entradas = [
        {"tema": "ok", "receptividad": "alta", "palabras_usuario": 1, "ts": ahora.isoformat()},
        {"tema": "ok", "receptividad": "alta", "palabras_usuario": 2, "ts": (ahora - timedelta(days=2)).isoformat()},
    ]
    rp.write_text(json.dumps(entradas), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    assert "ok" not in aikiu._temas_a_evitar()


def test_temas_evitar_ts_invalido_se_ignora(tmp_path, monkeypatch):
    rp = tmp_path / "recep.json"
    rp.write_text(json.dumps([
        {"tema": "x", "receptividad": "baja", "palabras_usuario": 1, "ts": "no-fecha"},
    ]), encoding="utf-8")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", rp)
    assert aikiu._temas_a_evitar() == []


# ---------------------------------------------------------------------------
# _temas_preferidos
# ---------------------------------------------------------------------------

def test_temas_preferidos_sin_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(aikiu, "STATS_PATH", tmp_path / "no.json")
    assert aikiu._temas_preferidos() == []


def test_temas_preferidos_con_ranking(tmp_path, monkeypatch):
    sp = tmp_path / "stats.json"
    sp.write_text(json.dumps({
        "2026-05-22": {"ranking_temas": ["cocina", "tango", "plantas"]},
    }), encoding="utf-8")
    monkeypatch.setattr(aikiu, "STATS_PATH", sp)
    assert aikiu._temas_preferidos() == ["cocina", "tango", "plantas"]


def test_temas_preferidos_sin_ranking_en_dia(tmp_path, monkeypatch):
    sp = tmp_path / "stats.json"
    sp.write_text(json.dumps({"2026-05-22": {"mensajes": 5}}), encoding="utf-8")
    monkeypatch.setattr(aikiu, "STATS_PATH", sp)
    assert aikiu._temas_preferidos() == []


# ---------------------------------------------------------------------------
# _actualizar_seccion_perfil
# ---------------------------------------------------------------------------

def test_actualizar_seccion_perfil_existente(tmp_path, monkeypatch):
    perfil = tmp_path / "perfil.md"
    perfil.write_text("# X\n\n## Aprendizajes\n- Viejo\n\n## Salud\n- presión\n", encoding="utf-8")
    monkeypatch.setattr(aikiu, "PERFIL_PATH", perfil)
    aikiu._actualizar_seccion_perfil("Aprendizajes", ["- nuevo dato"])
    contenido = perfil.read_text(encoding="utf-8")
    assert "- nuevo dato" in contenido
    assert "- Viejo" in contenido
    assert "## Salud" in contenido


def test_actualizar_seccion_perfil_inexistente_se_agrega(tmp_path, monkeypatch):
    perfil = tmp_path / "perfil.md"
    perfil.write_text("# X\n\n## Salud\n- presión", encoding="utf-8")
    monkeypatch.setattr(aikiu, "PERFIL_PATH", perfil)
    aikiu._actualizar_seccion_perfil("Ajustes sugeridos", ["- ser breve"])
    contenido = perfil.read_text(encoding="utf-8")
    assert "## Ajustes sugeridos" in contenido
    assert "- ser breve" in contenido


# ---------------------------------------------------------------------------
# create_background_task
# ---------------------------------------------------------------------------

def test_create_background_task_agrega_a_set():
    async def correr():
        async def trabajo():
            return 1
        task = aikiu.create_background_task(trabajo())
        assert task in aikiu._background_tasks
        await task
        await asyncio.sleep(0)
        assert task not in aikiu._background_tasks
    run(correr())


# ---------------------------------------------------------------------------
# programar_recordatorios
# ---------------------------------------------------------------------------

def test_programar_recordatorios_arma_jobs(monkeypatch):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    cfg = {
        "saludo_diario": {"activo": True, "hora": "08:30"},
        "recordatorios": [{"hora": "13:00", "mensaje": "Tomar pastilla"}],
        "analisis_nocturno_hora": "23:30",
        "alerta_inactividad": {"activa": True, "checks": ["11:30", "19:00"]},
    }
    monkeypatch.setattr(aikiu, "CONFIG", cfg)
    app = MagicMock()
    aikiu.programar_recordatorios(scheduler, app)
    jobs = scheduler.get_jobs()
    # saludo + 1 recordatorio + análisis nocturno + 2 checks inactividad = 5
    assert len(jobs) >= 4


def test_programar_recordatorios_saludo_off(monkeypatch):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    cfg = {
        "saludo_diario": {"activo": False, "hora": "08:30"},
        "recordatorios": [],
        "analisis_nocturno_hora": "23:30",
        "alerta_inactividad": {"activa": False},
    }
    monkeypatch.setattr(aikiu, "CONFIG", cfg)
    aikiu.programar_recordatorios(scheduler, MagicMock())
    jobs = scheduler.get_jobs()
    # Solo el análisis nocturno
    assert len(jobs) == 1


def test_programar_recordatorios_sin_saludo_diario(monkeypatch):
    """Sin la clave 'saludo_diario', usa default activo=True."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    cfg = {"analisis_nocturno_hora": "23:30", "alerta_inactividad": {"activa": False}}
    monkeypatch.setattr(aikiu, "CONFIG", cfg)
    aikiu.programar_recordatorios(scheduler, MagicMock())
    assert len(scheduler.get_jobs()) >= 2  # saludo default + análisis nocturno
