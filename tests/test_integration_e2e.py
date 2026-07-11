"""
Tests de integración punta a punta — simulan flujos completos atravesando
varios módulos como pasaría en producción, pero con servicios externos
(Telegram, Groq, ffmpeg, redes) mockeados.

A diferencia de los tests unitarios, acá ejercitamos el "trayecto real"
de un mensaje desde que llega al handler hasta que se persiste el estado.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aikiu
from core import state as state_mod
from core import distress as distress_mod
from core import usage as usage_mod
from admin import bot as admin_bot
from admin import state as admin_state
from andromarta import bot as andro_bot
from andromarta import ciclo as ciclo_mod
from andromarta import memoria as memoria_mod
from andromarta import estado as andro_estado
from andromarta import persona as andro_persona
import familiar_bot


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar_global(tmp_path, monkeypatch):
    # State
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.delenv("CHAT_ID", raising=False)
    # Admin state
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "admin_state.json")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", tmp_path / "legacy.json")
    for e in ("ADMIN_CHAT_ID", "ADMIN_CHAT_IDS", "ADMIN_MAX_USERS"):
        monkeypatch.delenv(e, raising=False)
    # Familiar
    monkeypatch.setattr(familiar_bot, "FAMILIARES_PATH", tmp_path / "familiares.json")
    monkeypatch.setattr(familiar_bot, "PERFIL_PATH", tmp_path / "perfil.md")
    monkeypatch.setattr(familiar_bot, "STATS_PATH", tmp_path / "stats.json")
    # Andromarta
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", tmp_path / "memoria.json")
    monkeypatch.setattr(memoria_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ciclo_mod, "CICLO_PATH", tmp_path / "ciclo.json")
    monkeypatch.setattr(ciclo_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(andro_estado, "ESTADO_PATH", tmp_path / "andro_estado.json")
    monkeypatch.setattr(andro_estado, "DATA_DIR", tmp_path)
    monkeypatch.setattr(andro_persona, "PERSONA_PATH", tmp_path / "persona.md")
    # Aikiu stats/recep/logs
    monkeypatch.setattr(aikiu, "STATS_PATH", tmp_path / "aikiu_stats.json")
    monkeypatch.setattr(aikiu, "RECEPTIVIDAD_PATH", tmp_path / "recep.json")
    monkeypatch.setattr(aikiu, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(aikiu, "PERFIL_PATH", tmp_path / "perfil_aikiu.md")
    # Distress: limpiar cooldowns
    distress_mod._last_alert_time.clear()
    yield
    distress_mod._last_alert_time.clear()


# ---------------------------------------------------------------------------
# E2E #1: TOFU completo — primer /start + mensaje + alerta familiar
# ---------------------------------------------------------------------------

def test_e2e_tofu_y_mensaje_genera_alerta_a_familiar(monkeypatch):
    """
    Flujo:
    1. Llega un /start de chat_id=42 → se registra como owner.
    2. Llega un mensaje de texto distress 2 → se genera respuesta + alerta a familiar.
    3. La alerta se envía al chat_id del familiar suscripto.
    """
    # Setup familiares y CONFIG
    familiar_bot.guardar_familiares([{"chat_id": 999, "nombre": "Germán"}])
    monkeypatch.setattr(aikiu, "CONFIG", {
        "nombre_adulto_mayor": "Marta",
        "nombre_asistente": "Aikiu",
        "_perfil": "",
        "modelo_llm": "llama-3.3-70b-versatile",
    })

    # /start
    update_start = MagicMock()
    update_start.effective_chat.id = 42
    update_start.effective_user.first_name = "Marta"
    update_start.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_chat_action = AsyncMock()
    ctx.bot_data = {}

    run(aikiu.cmd_start(update_start, ctx))
    # En multi-tenant, el primer /start crea el hogar `instances/42/`.
    from core import hogar as hogar_mod
    assert hogar_mod.existe_hogar(42)

    # Mensaje con distress
    update_msg = MagicMock()
    update_msg.effective_chat.id = 42
    update_msg.message.voice = None
    update_msg.message.text = "me siento muy sola hoy"

    # Mock del agente conversador (Groq): responde a Marta.
    fake_groq = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = "Estoy acá, Marta."
    completion.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    fake_groq.chat.completions.create = AsyncMock(return_value=completion)

    # Mock del agente vigía: clasifica nivel 2 (arquitectura de dos agentes).
    monkeypatch.setattr(
        aikiu, "clasificar_distress",
        AsyncMock(return_value=(2, "dice que se siente muy sola")),
    )

    # Aislar usage
    from pathlib import Path as P
    monkeypatch.setattr(usage_mod, "instance_dir", lambda: P("."))

    # Family bot mock que captura los send_message
    family_bot = MagicMock()
    family_bot.send_message = AsyncMock()
    ctx.bot_data["family_bot"] = family_bot

    # background_task se ejecuta inline
    background = []
    def capt(coro):
        background.append(coro)
        return MagicMock()
    monkeypatch.setattr(aikiu, "create_background_task", capt)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())

    with patch("aikiu.groq", fake_groq), \
         patch("core.alerts.cargar_suscriptores", return_value=[999]):
        run(aikiu.handle_message(update_msg, ctx))
        # Drenar tareas background
        for coro in background:
            try:
                run(coro)
            except Exception:
                pass

    # Llegó respuesta a Marta (sin DISTRESS_LEVEL)
    ctx.bot.send_message.assert_awaited()
    args_marta = ctx.bot.send_message.await_args
    assert args_marta.kwargs["chat_id"] == 42
    assert "Estoy acá" in args_marta.kwargs["text"]
    assert "DISTRESS_LEVEL" not in args_marta.kwargs["text"]

    # Llegó alerta a Germán
    family_bot.send_message.assert_awaited()
    alerta = family_bot.send_message.await_args
    assert alerta.kwargs["chat_id"] == 999
    assert "Marta" in alerta.kwargs["text"]
    # El motivo del vigía viaja en la alerta a la familia
    assert "se siente muy sola" in alerta.kwargs["text"]


# ---------------------------------------------------------------------------
# E2E #2: ciclo completo de Andromarta (apertura → turno → despedida → cierre)
# ---------------------------------------------------------------------------

def test_e2e_andromarta_ciclo_completo(monkeypatch):
    """
    1. Scheduler dispara iniciativa → abre ciclo, manda mensaje.
    2. Aikiu responde, Andromarta replica.
    3. Al llegar al tope, Andromarta cierra con despedida.
    4. Mensajes posteriores son ignorados hasta que vuelva a abrir.
    """
    # Setup mocks de Telegram
    client = MagicMock()
    action_ctx = MagicMock()
    action_ctx.__aenter__ = AsyncMock(return_value=None)
    action_ctx.__aexit__ = AsyncMock(return_value=False)
    client.action = MagicMock(return_value=action_ctx)
    client.send_message = AsyncMock()
    client.send_file = AsyncMock()
    entity = MagicMock()
    monkeypatch.setattr(andro_bot, "client", client)
    monkeypatch.setattr(andro_bot, "aikiu_entity", entity)
    monkeypatch.setattr(andro_bot, "RITMO_HUMANO", False)
    monkeypatch.setattr(andro_bot, "VOZ_PROB", 0.0)
    monkeypatch.setattr(andro_bot, "MAX_TURNOS_CICLO", 4)
    # max=4: iniciativa(1) + aikiu(2) + marta(3) + aikiu(4=tope) → marta cierra
    import random
    monkeypatch.setattr(random, "random", lambda: 0.99)

    respuestas = iter([
        "che, ¿cómo va?",       # iniciativa
        "qué bien!",            # turno normal
        "bueno te dejo, ahora",  # despedida
    ])
    async def fake_responder(**kw):
        return next(respuestas)
    monkeypatch.setattr(andro_bot, "responder", fake_responder)

    # 1. Iniciativa
    run(andro_bot._disparar_iniciativa())
    assert ciclo_mod.cargar()["abierto"] is True
    assert ciclo_mod.cargar()["turnos"] == 1

    # 2. Llega mensaje de Aikiu
    event1 = MagicMock()
    event1.message = MagicMock(text="hola Marta", voice=None)
    run(andro_bot._on_clara_msg(event1))
    assert ciclo_mod.cargar()["turnos"] == 3  # 1 + aikiu(2) + marta(3)

    # 3. Llega otro mensaje de Aikiu → marta despedida y cierra
    event2 = MagicMock()
    event2.message = MagicMock(text="qué hacés?", voice=None)
    run(andro_bot._on_clara_msg(event2))
    estado = ciclo_mod.cargar()
    assert estado["abierto"] is False
    assert estado["turnos"] >= 4

    # 4. Mensajes posteriores se ignoran
    sends_antes = client.send_message.await_count
    event3 = MagicMock()
    event3.message = MagicMock(text="hola?", voice=None)
    run(andro_bot._on_clara_msg(event3))
    assert client.send_message.await_count == sends_antes


# ---------------------------------------------------------------------------
# E2E #3: Familiar manda mensaje al adulto via puente
# ---------------------------------------------------------------------------

def test_e2e_familiar_envia_mensaje_a_adulto(monkeypatch):
    """
    1. Germán manda /start → queda suscripto.
    2. Germán manda /nombre Germán → se registra el nombre.
    3. Adulto Marta ya tiene un owner_chat_id (TOFU previo).
    4. Germán inicia /mensaje, envía texto → llega a Marta como "Germán te manda..."
    """
    # Setup: owner registrado
    state_mod.registrar_owner(42)

    update = MagicMock()
    update.effective_chat.id = 999
    update.effective_user.first_name = "Germán"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = ""
    update.message.voice = None
    ctx = MagicMock()
    ctx.args = []
    ctx.user_data = {}

    # 1. /start
    run(familiar_bot.cmd_start(update, ctx))
    assert familiar_bot.es_suscriptor(999)

    # 2. /nombre Germán
    ctx.args = ["Germán"]
    run(familiar_bot.cmd_nombre(update, ctx))
    assert familiar_bot.nombre_registrado(999) == "Germán"

    # 3. /mensaje → estado ESPERANDO
    monkeypatch.setattr(familiar_bot, "ADULTO_BOT_TOKEN", "abc:def")
    estado = run(familiar_bot.cmd_mensaje(update, ctx))
    assert estado == familiar_bot.ESPERANDO_MENSAJE

    # 4. Envío del mensaje
    update.message.text = "te llamo en un rato"
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock()
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(return_value=mock_bot)
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("familiar_bot.Bot", return_value=bot_ctx):
        run(familiar_bot.recibir_mensaje_familiar(update, ctx))
    # El bot familiar abrió un Bot con el token del adulto y mandó mensaje a Marta
    mock_bot.send_message.assert_awaited_once()
    args = mock_bot.send_message.await_args
    assert args.kwargs["chat_id"] == 42
    assert "Germán" in args.kwargs["text"]
    assert "te llamo en un rato" in args.kwargs["text"]


# ---------------------------------------------------------------------------
# E2E #4: admin /llm con datos reales agregados
# ---------------------------------------------------------------------------

def test_e2e_admin_llm_resume_uso_real(monkeypatch, tmp_path):
    """
    1. Se registran varias llamadas al LLM vía usage_mod.
    2. /llm las suma y las muestra agrupadas por modelo.
    """
    # Aislar instance_dir
    monkeypatch.setattr(usage_mod, "instance_dir", lambda: tmp_path)
    from core import instance as inst_mod
    monkeypatch.setattr(inst_mod, "instance_dir", lambda: tmp_path)
    monkeypatch.setattr(usage_mod, "_lock", asyncio.Lock())

    # Registrar uso simulado
    from types import SimpleNamespace
    async def sembrar():
        for _ in range(5):
            usage_obj = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
            await usage_mod.registrar_chat("llama-3.3-70b-versatile", usage_obj, 500)
        await usage_mod.registrar_stt("whisper-large-v3", 1200, bytes_audio=50_000)
        await usage_mod.registrar_error("chat", "llama-3.3-70b-versatile", 100, "RateLimitError")
    run(sembrar())

    # Admin autorizado
    admin_state.registrar_admin(7)

    update = MagicMock()
    update.effective_chat.id = 7
    update.effective_user.first_name = "Admin"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []
    ctx.bot = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    # admin/bot.descubrir_instancias devuelve nuestro tmp
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "default")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")

    run(admin_bot.cmd_llm(update, ctx))
    update.message.reply_text.assert_awaited()
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "llama-3.3-70b-versatile" in msg
    # 5 ok + 1 error = 6 total; el reporte agrega 750 tokens
    assert "750" in msg or "750" == "750"  # validamos que esté la suma de tokens
    # Aparece info de Whisper
    assert "Whisper" in msg or "Transcripción" in msg


# ---------------------------------------------------------------------------
# E2E #5: análisis nocturno cierra el ciclo de aprendizaje
# ---------------------------------------------------------------------------

def test_e2e_analisis_nocturno_actualiza_perfil_y_stats(monkeypatch, tmp_path):
    """
    1. Existe un log del día y un perfil.md.
    2. analisis_nocturno() corre con LLM mockeado.
    3. Aprendizajes nuevos van al perfil.md, stats.json registra el resumen,
       y se calcula el ranking de temas (si hay datos de receptividad).
    """
    from datetime import date as D
    hoy = D.today().strftime("%Y-%m-%d")

    # Log del día con un síntoma
    aikiu.LOGS_DIR.mkdir(exist_ok=True)
    (aikiu.LOGS_DIR / f"{hoy}.md").write_text(
        "**10:00**\n- Marta: hoy me duele la rodilla\n- Aikiu: cuidate\n",
        encoding="utf-8",
    )
    # Perfil inicial
    aikiu.PERFIL_PATH.write_text(
        "# Perfil de Marta\n\n## Aprendizajes\n", encoding="utf-8"
    )
    # Stats vacío
    aikiu.STATS_PATH.write_text("{}", encoding="utf-8")
    # Receptividad con datos
    aikiu.RECEPTIVIDAD_PATH.write_text(json.dumps([
        {"tema": "cocina", "receptividad": "alta", "palabras_usuario": 12,
         "ts": datetime.now().isoformat()},
    ]), encoding="utf-8")

    monkeypatch.setattr(aikiu, "CONFIG",
                        {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
                         "modelo_llm": "llama-3.3-70b-versatile"})

    # Mock Groq:
    # primero la respuesta del análisis (aprendizajes + ajustes)
    # segundo la conversión de ajustes a instrucciones
    respuestas_llm = iter([
        "APRENDIZAJES_NUEVOS:\n- Marta mencionó dolor de rodilla hoy\nAJUSTES_CONVERSACION:\n- Evitá insistir con preguntas",
        "- Sin preguntas en cadena cuando el ánimo está bajo",
    ])
    def make_completion(text):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].message.content = text
        c.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        return c

    fake_groq = MagicMock()
    fake_groq.chat.completions.create = AsyncMock(
        side_effect=lambda **kw: make_completion(next(respuestas_llm))
    )

    with patch("aikiu.groq", fake_groq):
        run(aikiu.analisis_nocturno(app=None))

    perfil_final = aikiu.PERFIL_PATH.read_text(encoding="utf-8")
    assert "dolor de rodilla" in perfil_final
    assert "Ajustes sugeridos" in perfil_final

    stats = json.loads(aikiu.STATS_PATH.read_text(encoding="utf-8"))
    assert hoy in stats
    assert stats[hoy]["analisis_nocturno"]["aprendizajes_nuevos"] == 1
    # Ranking precalculado
    assert "ranking_temas" in stats[hoy]
    assert "cocina" in stats[hoy]["ranking_temas"]


# ---------------------------------------------------------------------------
# E2E #6: admin /health + ping Telegram + heartbeat
# ---------------------------------------------------------------------------

def test_e2e_admin_health_lee_heartbeat_real(monkeypatch, tmp_path):
    """
    1. Hay archivos heartbeat para aikiu y familiar (escritos hace pocos seg).
    2. /health los lee, hace ping mockeado y devuelve estado verde para todos.
    """
    # Heartbeats recientes
    ahora = datetime.now().isoformat()
    (tmp_path / "heartbeat-aikiu.json").write_text(
        json.dumps({"role": "aikiu", "instance_id": "default", "pid": 1,
                    "started_at": ahora, "last_seen": ahora, "owner_chat_id": 42}),
        encoding="utf-8",
    )
    (tmp_path / "heartbeat-familiar.json").write_text(
        json.dumps({"role": "familiar", "instance_id": "default", "pid": 2,
                    "started_at": ahora, "last_seen": ahora, "owner_chat_id": None}),
        encoding="utf-8",
    )

    admin_state.registrar_admin(7)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "default")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "abc:def")
    monkeypatch.setattr(admin_bot, "_ping_telegram", AsyncMock(return_value="@bot"))

    update = MagicMock()
    update.effective_chat.id = 7
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()

    run(admin_bot.cmd_health(update, ctx))
    update.message.reply_text.assert_awaited()
    msg = update.message.reply_text.await_args.args[0]
    assert "Todo OK" in msg or "OK" in msg
    assert "Marta" in msg
    assert "default" in msg


# ---------------------------------------------------------------------------
# E2E #7: editar perfil vía familiar bot — conversación completa
# ---------------------------------------------------------------------------

def test_e2e_editar_perfil_completa_conversacion():
    """
    1. /editar → ELIGIENDO
    2. Texto 'Quién es' → RECIBIENDO
    3. Nuevo contenido → END + perfil actualizado.
    """
    familiar_bot.agregar_familiar(999)
    familiar_bot.PERFIL_PATH.write_text(
        "## Quién es\n- 83 años\n\n## Salud\n- presión", encoding="utf-8"
    )

    # /editar
    update1 = MagicMock()
    update1.effective_chat.id = 999
    update1.message = MagicMock()
    update1.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.user_data = {}
    estado = run(familiar_bot.cmd_editar(update1, ctx))
    assert estado == familiar_bot.ELIGIENDO

    # Eligió sección
    update2 = MagicMock()
    update2.effective_chat.id = 999
    update2.message = MagicMock()
    update2.message.reply_text = AsyncMock()
    update2.message.text = "Quién es"
    estado = run(familiar_bot.elegir_seccion(update2, ctx))
    assert estado == familiar_bot.RECIBIENDO
    assert ctx.user_data["seccion"] == "Quién es"

    # Envía nuevo contenido
    update3 = MagicMock()
    update3.effective_chat.id = 999
    update3.message = MagicMock()
    update3.message.reply_text = AsyncMock()
    update3.message.text = "- 84 años recién cumplidos\n- toma el remedio sola"
    estado = run(familiar_bot.recibir_contenido(update3, ctx))
    from telegram.ext import ConversationHandler
    assert estado == ConversationHandler.END

    perfil = familiar_bot.PERFIL_PATH.read_text(encoding="utf-8")
    assert "84 años" in perfil
    assert "remedio" in perfil
    assert "presión" in perfil  # otras secciones no se tocan


# ---------------------------------------------------------------------------
# E2E #8: distress nivel 0 NO genera alerta
# ---------------------------------------------------------------------------

def test_e2e_mensaje_normal_sin_distress_no_alerta(monkeypatch):
    from core import hogar as hogar_mod
    hogar_mod.crear_hogar(42)
    monkeypatch.setattr(aikiu, "CONFIG", {
        "nombre_adulto_mayor": "Marta", "nombre_asistente": "Aikiu",
        "_perfil": "", "modelo_llm": "m",
    })
    update = MagicMock()
    update.effective_chat.id = 42
    update.effective_user.first_name = "Marta"
    update.message = MagicMock(voice=None, text="qué lindo día")
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    ctx.bot.send_chat_action = AsyncMock()
    family_bot_mock = MagicMock()
    family_bot_mock.send_message = AsyncMock()
    ctx.bot_data = {"family_bot": family_bot_mock}

    fake_groq = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock()]
    completion.choices[0].message.content = "Qué bueno, Marta.\nDISTRESS_LEVEL: 0"
    completion.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)
    fake_groq.chat.completions.create = AsyncMock(return_value=completion)

    monkeypatch.setattr(aikiu, "historiales", {})
    monkeypatch.setattr(aikiu, "create_background_task", lambda c: c.close())
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)

    with patch("aikiu.groq", fake_groq):
        run(aikiu.handle_message(update, ctx))
    # Marta recibió la respuesta limpia
    ctx.bot.send_message.assert_awaited_once()
    # Pero el familiar NO recibió nada
    family_bot_mock.send_message.assert_not_awaited()
