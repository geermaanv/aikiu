"""
Tests end-to-end del flujo multi-hogar.

Simulan los caminos críticos punta-a-punta:

1. Dos adultos distintos hacen /start: cada uno tiene su propio hogar
   aislado.
2. Un familiar se vincula a los dos adultos via /invitar + /vincular, y
   los comandos del familiar operan sobre el adulto activo.
3. Las alertas (notify_family) llegan SOLO al familiar correcto, con el
   nombre del adulto correcto.
4. Borrado de un hogar via admin /borrar deja al otro intacto.
5. Migración legacy ejecutada al arranque queda como hogar normal y
   conserva los datos.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import aikiu
import familiar_bot
from admin import bot as admin_bot
from admin import state as admin_state
from core import alerts as alerts_mod
from core import distress as distress_mod
from core import familiar_state as fs
from core import hogar as hogar_mod
from core import invites as invites_mod
from core import migrate_legacy as migrate_mod
from core import state as state_mod


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    registry = tmp_path / "registry"
    registry.mkdir()
    monkeypatch.setenv("AIKIU_REGISTRY", str(registry))
    monkeypatch.setattr(state_mod, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "admin_state.json")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", tmp_path / "legacy.json")
    monkeypatch.setattr(familiar_bot, "FAMILIARES_PATH", tmp_path / "familiares.json")
    monkeypatch.setattr(familiar_bot, "PERFIL_PATH", tmp_path / "perfil.md")
    monkeypatch.setattr(familiar_bot, "STATS_PATH", tmp_path / "stats.json")
    for e in ("CHAT_ID", "ADMIN_CHAT_ID", "ADMIN_CHAT_IDS", "ADMIN_MAX_USERS"):
        monkeypatch.delenv(e, raising=False)
    distress_mod.reset_cooldowns()
    yield
    distress_mod.reset_cooldowns()


def _fake_update_aikiu(chat_id, first_name="Marta"):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


def _fake_context_aikiu(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


def _fake_update_familiar(chat_id, first_name="Lao", text=""):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.text = text
    update.message.voice = None
    update.message.reply_text = AsyncMock()
    return update


def _fake_context_familiar(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    return ctx


# ---------------------------------------------------------------------------
# E2E #1 — Dos adultos hacen /start: hogares aislados
# ---------------------------------------------------------------------------

def test_e2e_dos_adultos_hacen_start_hogares_separados():
    update_marta = _fake_update_aikiu(1001, first_name="Marta")
    update_pepe = _fake_update_aikiu(2002, first_name="Pepe")
    ctx = _fake_context_aikiu()
    with patch("aikiu.CONFIG", {"nombre_adulto_mayor": "Marta", "nombre_asistente": "Clara"}):
        run(aikiu.cmd_start(update_marta, ctx))
        run(aikiu.cmd_start(update_pepe, ctx))

    assert hogar_mod.existe_hogar(1001)
    assert hogar_mod.existe_hogar(2002)
    assert sorted(hogar_mod.listar_hogares()) == [1001, 2002]
    # Los directorios son distintos
    assert hogar_mod.hogar_dir(1001) != hogar_mod.hogar_dir(2002)


# ---------------------------------------------------------------------------
# E2E #2 — Un familiar vinculado a dos adultos navega entre ellos
# ---------------------------------------------------------------------------

def test_e2e_familiar_vinculado_a_dos_adultos_y_perfil_correcto():
    # Setup: dos adultos con perfiles distintos
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")
    hogar_mod.perfil_path(1001).write_text("# Marta\n\nperfil de Marta", encoding="utf-8")
    hogar_mod.perfil_path(2002).write_text("# Pepe\n\nperfil de Pepe", encoding="utf-8")

    # Familiar entra y se vincula a ambos usando códigos de invitación
    run(familiar_bot.cmd_start(_fake_update_familiar(500, first_name="Lao"), _fake_context_familiar()))
    codigo_marta = invites_mod.generar_codigo(1001)
    codigo_pepe = invites_mod.generar_codigo(2002)
    run(familiar_bot.cmd_vincular(_fake_update_familiar(500), _fake_context_familiar(args=[codigo_marta])))
    run(familiar_bot.cmd_vincular(_fake_update_familiar(500), _fake_context_familiar(args=[codigo_pepe])))

    assert sorted(fs.adultos_de(500)) == [1001, 2002]
    assert fs.adulto_activo(500) == 1001  # el primero queda activo

    # /perfil con adulto activo = Marta
    update = _fake_update_familiar(500)
    run(familiar_bot.cmd_perfil(update, _fake_context_familiar()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "perfil de Marta" in msg

    # Cambio el activo a Pepe
    run(familiar_bot.cmd_elegir(_fake_update_familiar(500), _fake_context_familiar(args=["2002"])))
    assert fs.adulto_activo(500) == 2002

    # /perfil ahora trae el de Pepe
    update = _fake_update_familiar(500)
    run(familiar_bot.cmd_perfil(update, _fake_context_familiar()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Pepe" in msg
    assert "perfil de Pepe" in msg


# ---------------------------------------------------------------------------
# E2E #3 — Las alertas distress llegan solo a familiares del adulto correcto
# ---------------------------------------------------------------------------

def test_e2e_alerta_distress_aislada_por_hogar():
    # Dos adultos, dos familiares distintos
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")
    # Lao vinculado a Marta solo
    fams_marta = hogar_mod.familiares_path(1001)
    fams_marta.write_text(json.dumps([{"chat_id": 500, "nombre": "Lao"}]), encoding="utf-8")
    # Ana vinculada a Pepe solo
    fams_pepe = hogar_mod.familiares_path(2002)
    fams_pepe.write_text(json.dumps([{"chat_id": 600, "nombre": "Ana"}]), encoding="utf-8")

    bot = MagicMock()
    bot.send_message = AsyncMock()

    # Alerta sobre Marta → solo Lao
    run(alerts_mod.notify_family(
        distress_level=2,
        adulto_message="no estoy bien",
        bot_response="vamos a estar bien",
        family_bot=bot,
        adulto_chat_id=1001,
    ))
    chat_ids_destinatarios = [
        call.kwargs["chat_id"]
        for call in bot.send_message.await_args_list
    ]
    assert chat_ids_destinatarios == [500]
    assert "Marta" in bot.send_message.await_args.kwargs["text"]
    bot.send_message.reset_mock()

    # Alerta sobre Pepe → solo Ana
    run(alerts_mod.notify_family(
        distress_level=2,
        adulto_message="me duele",
        bot_response="quedate quieto",
        family_bot=bot,
        adulto_chat_id=2002,
    ))
    chat_ids_destinatarios = [
        call.kwargs["chat_id"]
        for call in bot.send_message.await_args_list
    ]
    assert chat_ids_destinatarios == [600]
    assert "Pepe" in bot.send_message.await_args.kwargs["text"]


# ---------------------------------------------------------------------------
# E2E #3b — El cooldown de distress es por hogar (no se contagia entre adultos)
# ---------------------------------------------------------------------------

def test_e2e_cooldown_distress_aislado_por_hogar():
    """Si Marta (1001) dispara nivel 2, una alerta nivel 2 de Pepe (2002)
    en los próximos 30 minutos NO debe ser bloqueada por el cooldown."""
    # Marta dispara una alerta nivel 2 — desde ahora hay cooldown para 1001.
    assert distress_mod.should_send_alert(2, adulto_chat_id=1001) is True
    distress_mod.record_alert_sent(2, adulto_chat_id=1001)

    # Inmediatamente después, Marta NO puede mandar otra (cooldown 30 min).
    assert distress_mod.should_send_alert(2, adulto_chat_id=1001) is False

    # Pero Pepe (otro hogar) SÍ puede — su reloj es independiente.
    assert distress_mod.should_send_alert(2, adulto_chat_id=2002) is True
    distress_mod.record_alert_sent(2, adulto_chat_id=2002)
    # Ya cuenta para Pepe también.
    assert distress_mod.should_send_alert(2, adulto_chat_id=2002) is False

    # Nivel 3 ignora cooldown — emergencia activa.
    assert distress_mod.should_send_alert(3, adulto_chat_id=1001) is True
    assert distress_mod.should_send_alert(3, adulto_chat_id=2002) is True


# ---------------------------------------------------------------------------
# E2E #4 — Borrar un hogar deja al otro intacto
# ---------------------------------------------------------------------------

def test_e2e_borrar_un_hogar_no_afecta_al_otro():
    admin_state.registrar_admin(7)
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")
    hogar_mod.perfil_path(2002).write_text("perfil de Pepe", encoding="utf-8")

    update = MagicMock()
    update.effective_chat.id = 7
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["1001", "CONFIRMAR"]
    run(admin_bot.cmd_borrar(update, ctx))

    assert not hogar_mod.existe_hogar(1001)
    assert hogar_mod.existe_hogar(2002)
    # Pepe sigue con sus datos
    assert "perfil de Pepe" in hogar_mod.perfil_path(2002).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# E2E #4b — Borrar un hogar limpia invitaciones pendientes y reasigna
#            el adulto activo del familiar que lo tenía como default
# ---------------------------------------------------------------------------

def test_e2e_borrar_hogar_purga_invites_y_reasigna_familiar():
    """El admin borra el hogar de Marta. Esto debe:
    1. Eliminar los códigos de invitación vivos que apuntaban a Marta.
    2. Reasignar el adulto activo del familiar que tenía a Marta como
       default, dejándolo apuntando a otro vínculo (si lo tiene)."""
    admin_state.registrar_admin(7)
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")

    # Familiar 500 está vinculado a Marta Y Pepe, con Marta como activo.
    fs.vincular(500, 1001, nombre="Lao")
    fs.vincular(500, 2002, nombre="Lao")
    fs.setear_adulto_activo(500, 1001)

    # Generamos códigos vivos de los dos hogares.
    cod_marta = invites_mod.generar_codigo(1001)
    cod_pepe = invites_mod.generar_codigo(2002)

    update = MagicMock()
    update.effective_chat.id = 7
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["1001", "CONFIRMAR"]
    run(admin_bot.cmd_borrar(update, ctx))

    # Hogar borrado
    assert not hogar_mod.existe_hogar(1001)
    # Códigos de Marta limpiados, los de Pepe intactos
    data = invites_mod._leer()
    assert cod_marta not in data
    assert cod_pepe in data
    # Familiar reasignado a Pepe (su otro vínculo)
    assert fs.adulto_activo(500) == 2002
    # Mensaje al admin menciona la limpieza
    msg = update.message.reply_text.await_args.args[0]
    assert "código" in msg.lower() or "familiar" in msg.lower()


# ---------------------------------------------------------------------------
# E2E #4c — Un código de un hogar borrado NO puede vincular a nadie
# ---------------------------------------------------------------------------

def test_e2e_codigo_de_hogar_borrado_no_vincula():
    """Defensa-en-profundidad: aunque por algún bug un código viejo no se
    purgara, intentar consumirlo después de borrar el hogar no debe
    asociar al familiar a un hogar fantasma."""
    hogar_mod.crear_hogar(1001, nombre="Marta")
    codigo = invites_mod.generar_codigo(1001)

    # El familiar tiene que pasar por /start primero (gate del bot familiar).
    run(familiar_bot.cmd_start(_fake_update_familiar(500, first_name="Lao"),
                                _fake_context_familiar()))

    # Borramos el hogar directamente (sin pasar por cmd_borrar, así no se
    # purgan los códigos automáticamente — simulando el peor escenario).
    hogar_mod.borrar_hogar(1001)

    # Familiar intenta usar el código.
    update = _fake_update_familiar(500, first_name="Lao")
    run(familiar_bot.cmd_vincular(update, _fake_context_familiar(args=[codigo])))

    # No quedó vinculado a nada y el mensaje le dice por qué.
    assert fs.adultos_de(500) == []
    msg = update.message.reply_text.await_args.args[0]
    assert (
        "no es válido" in msg.lower()
        or "expir" in msg.lower()
        or "no existe" in msg.lower()
    )


# ---------------------------------------------------------------------------
# E2E #5 — Migración legacy: el adulto histórico queda como hogar normal
# ---------------------------------------------------------------------------

def test_e2e_migracion_legacy_genera_hogar_y_conserva_datos(tmp_path, monkeypatch):
    """Simulamos una instalación single-tenant vieja: archivos en la raíz
    del repo (BASE_DIR), y verificamos que `migrar_si_corresponde` los
    mueve al hogar correspondiente."""
    repo = tmp_path / "fake_repo"
    repo.mkdir()
    registry = tmp_path / "fake_registry"
    registry.mkdir()
    monkeypatch.setenv("AIKIU_REGISTRY", str(registry))
    monkeypatch.setattr(migrate_mod, "BASE_DIR", repo)
    monkeypatch.setattr(hogar_mod, "BASE_DIR", repo)

    # Archivos legacy en la raíz
    (repo / "state.json").write_text(
        json.dumps({"owner_chat_id": 9999, "registered_at": "2026-01-01"}),
        encoding="utf-8",
    )
    (repo / "perfil.md").write_text("# Marta\n\nperfil legacy", encoding="utf-8")
    (repo / "stats.json").write_text(json.dumps({"2026-05-22": {"mensajes": 5}}), encoding="utf-8")

    owner = migrate_mod.migrar_si_corresponde()

    assert owner == 9999
    assert hogar_mod.existe_hogar(9999)
    assert not (repo / "state.json").exists()  # se movió
    assert "perfil legacy" in hogar_mod.perfil_path(9999).read_text(encoding="utf-8")
    stats = json.loads(hogar_mod.stats_path(9999).read_text(encoding="utf-8"))
    assert stats["2026-05-22"]["mensajes"] == 5
    # Marca de migración para auditoría desde /hogares
    estado = hogar_mod.leer_state(9999)
    assert estado.get("migrated_from_legacy") is True


# ---------------------------------------------------------------------------
# E2E #6 — /hogares del admin lista correctamente
# ---------------------------------------------------------------------------

def test_e2e_admin_metricas_muestra_bloque_por_hogar():
    """/metricas en modo multi-tenant tiene que mostrar un bloque por
    cada hogar (tráfico, suscripciones, alertas) además del bloque de
    procesos/LLM globales."""
    admin_state.registrar_admin(7)
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")
    # Datos distintos en cada hogar para verificar el bloque por hogar
    hogar_mod.stats_path(1001).write_text(
        json.dumps({"2026-05-22": {"mensajes": 7, "distress": {"1": 1, "2": 0, "3": 0}}}),
        encoding="utf-8",
    )
    hogar_mod.stats_path(2002).write_text(
        json.dumps({"2026-05-22": {"mensajes": 3, "distress": {"1": 0, "2": 0, "3": 0}}}),
        encoding="utf-8",
    )
    hogar_mod.familiares_path(1001).write_text(
        json.dumps([{"chat_id": 501, "nombre": "Lao"}]), encoding="utf-8"
    )

    update = MagicMock()
    update.effective_chat.id = 7
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []

    # Patcheamos las dependencias caras / con I/O real
    with patch.object(admin_bot.hb_mod, "leer_heartbeats",
                      return_value={"aikiu": None, "familiar": None}), \
         patch.object(admin_bot.usage_mod, "resumir",
                      return_value={"total_llamadas": 0, "errores": 0, "por_modelo": {}}):
        run(admin_bot.cmd_metricas(update, ctx))

    msg = update.message.reply_text.await_args.args[0]
    # Encabezado nuevo de bloque por hogar
    assert "Hogares multi-tenant" in msg
    # Cada hogar aparece nominado
    assert "Marta" in msg
    assert "Pepe" in msg
    assert "1001" in msg
    assert "2002" in msg


def test_e2e_admin_instancias_dice_n_hogares():
    """/instancias debe avisar al admin que un solo proceso atiende a N
    hogares multi-tenant. Si no lo dice, el operador confunde 'una
    instancia' con 'un hogar' y se piensa que el deploy está roto."""
    admin_state.registrar_admin(7)
    hogar_mod.crear_hogar(1001, nombre="Marta")
    hogar_mod.crear_hogar(2002, nombre="Pepe")

    update = MagicMock()
    update.effective_chat.id = 7
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []

    with patch.object(admin_bot, "descubrir_instancias",
                      return_value=[hogar_mod.instances_root() / "default"]), \
         patch.object(admin_bot.hb_mod, "leer_heartbeats",
                      return_value={"aikiu": None, "familiar": None}):
        run(admin_bot.cmd_instancias(update, ctx))

    msg = update.message.reply_text.await_args.args[0]
    assert "2 hogar" in msg.lower() or "hogares" in msg.lower()
    assert "/hogares" in msg


def test_e2e_admin_hogares_lista_dos_y_marca_migrado():
    admin_state.registrar_admin(7)
    hogar_mod.crear_hogar(1001, nombre="Marta")
    # Simulamos que el segundo fue migrado del legacy
    hogar_mod.crear_hogar(2002, nombre="Pepe", con_state=False)
    hogar_mod._escribir_json_atomico(
        hogar_mod.state_path(2002),
        {
            "owner_chat_id": 2002,
            "nombre_adulto": "Pepe",
            "registered_at": "2026-01-01",
            "migrated_from_legacy": True,
        },
    )

    update = MagicMock()
    update.effective_chat.id = 7
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = []
    run(admin_bot.cmd_hogares(update, ctx))

    msg = update.message.reply_text.await_args.args[0]
    assert "1001" in msg
    assert "2002" in msg
    assert "Marta" in msg
    assert "Pepe" in msg
    assert "migrado" in msg.lower()
