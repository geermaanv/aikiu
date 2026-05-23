"""Tests para admin/bot.py — handlers de comandos del bot de administración.

Estrategia:
- Importamos el módulo ya cargado por conftest (los env tokens dummy permiten
  el import sin errores). Cada test patchea lo que necesita (admin_state,
  descubrir_instancias, usage, heartbeat...).
- Para cada handler armamos un Update fake y un Context fake mínimos.
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin import bot as admin_bot
from admin import state as admin_state


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers para armar update / context
# ---------------------------------------------------------------------------

def _fake_update(chat_id=42, first_name="Ariel", text=""):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.first_name = first_name
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.message.text = text
    return update


def _fake_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.bot = MagicMock()
    ctx.bot.send_chat_action = AsyncMock()
    return ctx


@pytest.fixture(autouse=True)
def _aislar_admin_state(tmp_path, monkeypatch):
    """Cada test arranca con admin_state limpio (sin admins, sin env override)."""
    monkeypatch.setattr(admin_state, "ADMIN_STATE_PATH", tmp_path / "admin_state.json")
    monkeypatch.setattr(admin_state, "LEGACY_ADMIN_STATE_PATH", tmp_path / "legacy_admin_state.json")
    for env_var in ("ADMIN_CHAT_ID", "ADMIN_CHAT_IDS", "ADMIN_MAX_USERS"):
        monkeypatch.delenv(env_var, raising=False)
    yield


# ---------------------------------------------------------------------------
# Helpers puros (no async)
# ---------------------------------------------------------------------------

def test_hace_devuelve_guion_si_none():
    assert admin_bot._hace(None) == "—"


def test_hace_ahora_si_delta_negativo():
    futuro = (datetime.now() + timedelta(seconds=10)).isoformat()
    assert admin_bot._hace(futuro) == "ahora"


def test_hace_segundos():
    ahora = datetime(2026, 5, 22, 15, 0, 0)
    hace_30s = (ahora - timedelta(seconds=30)).isoformat()
    assert admin_bot._hace(hace_30s, ahora=ahora) == "hace 30s"


def test_hace_minutos():
    ahora = datetime(2026, 5, 22, 15, 0, 0)
    assert admin_bot._hace((ahora - timedelta(minutes=4)).isoformat(), ahora=ahora) == "hace 4 min"


def test_hace_horas_sin_minutos():
    ahora = datetime(2026, 5, 22, 15, 0, 0)
    assert admin_bot._hace((ahora - timedelta(hours=2)).isoformat(), ahora=ahora) == "hace 2h"


def test_hace_horas_con_minutos():
    ahora = datetime(2026, 5, 22, 15, 0, 0)
    assert admin_bot._hace(
        (ahora - timedelta(hours=2, minutes=30)).isoformat(),
        ahora=ahora,
    ) == "hace 2h 30min"


def test_hace_dias():
    ahora = datetime(2026, 5, 22, 15, 0, 0)
    assert admin_bot._hace((ahora - timedelta(days=3)).isoformat(), ahora=ahora) == "hace 3d"


def test_hace_iso_invalido_devuelve_string_crudo():
    assert admin_bot._hace("no-es-iso") == "no-es-iso"


def test_peor_devuelve_peor_estado():
    assert admin_bot._peor(["verde", "verde", "amarillo"]) == "amarillo"
    assert admin_bot._peor(["verde", "rojo", "amarillo"]) == "rojo"
    assert admin_bot._peor(["amarillo", "ausente"]) == "ausente"


def test_peor_lista_vacia():
    assert admin_bot._peor([]) == "ausente"


def test_sparkline_devuelve_unicode():
    sp = admin_bot._sparkline([1, 2, 4, 7, 3])
    assert len(sp) == 5
    # Caracteres unicode de blocks
    chars = "▁▂▃▄▅▆▇█"
    assert all(c in chars for c in sp)


def test_sparkline_vacio_es_string_vacio():
    assert admin_bot._sparkline([]) == ""


def test_sparkline_todos_cero():
    sp = admin_bot._sparkline([0, 0, 0])
    assert len(sp) == 3


def test_formato_bytes_b():
    assert admin_bot._formato_bytes(500) == "500 B"


def test_formato_bytes_kb():
    assert admin_bot._formato_bytes(1500) == "1.5 KB"


def test_formato_bytes_mb():
    assert "MB" in admin_bot._formato_bytes(2 * 1024 * 1024)


def test_formato_bytes_gb():
    assert "GB" in admin_bot._formato_bytes(3 * 1024 * 1024 * 1024)


def test_formato_tokens_corto():
    assert admin_bot._formato_tokens(500) == "500"


def test_formato_tokens_mil():
    assert admin_bot._formato_tokens(1234) == "1,2k"


def test_formato_tokens_decenas_de_miles():
    assert admin_bot._formato_tokens(45_000) == "45k"


def test_formato_tokens_millones():
    assert admin_bot._formato_tokens(2_500_000) == "2,5 M"


def test_plural():
    assert admin_bot._plural(1, "error", "errores") == "error"
    assert admin_bot._plural(0, "error", "errores") == "errores"
    assert admin_bot._plural(5, "error", "errores") == "errores"


def test_formato_latencia_ms():
    assert admin_bot._formato_latencia(812) == "812ms"


def test_formato_latencia_segundos():
    assert admin_bot._formato_latencia(1500) == "1,5s"


def test_latencia_p50_vacia():
    assert admin_bot._latencia_p50([]) == "—"


def test_latencia_p50_pocos_samples_muestra_n():
    res = admin_bot._latencia_p50([100, 200])
    assert "n=2" in res


def test_latencia_p50_muchos_samples_no_muestra_n():
    res = admin_bot._latencia_p50([100, 200, 300, 400, 500, 600])
    assert "n=" not in res


def test_semaforo_limite_sin_tpd():
    emoji, descr, pct = admin_bot._semaforo_limite(100, None)
    assert emoji == "⚪"
    assert pct == "—"


def test_semaforo_limite_consumo_bajo():
    emoji, descr, pct = admin_bot._semaforo_limite(100, 100_000)
    assert emoji == "🟢"
    assert "bajo" in descr


def test_semaforo_limite_consumo_alto():
    emoji, _, pct = admin_bot._semaforo_limite(75_000, 100_000)
    assert emoji == "🟡"


def test_semaforo_limite_casi_al_tope():
    emoji, _, pct = admin_bot._semaforo_limite(95_000, 100_000)
    assert emoji == "🔴"


def test_semaforo_limite_porcentaje_chico_se_muestra_como_menor_1():
    emoji, _, pct = admin_bot._semaforo_limite(10, 100_000)
    assert pct == "<1%"


def test_semaforo_limite_tpd_cero():
    emoji, _, pct = admin_bot._semaforo_limite(10, 0)
    assert emoji == "⚪"


def test_tpd_efectivo_usa_override(monkeypatch):
    monkeypatch.setattr(admin_bot, "LIMITE_TOKENS_DIA_OVERRIDE", 50_000)
    assert admin_bot._tpd_efectivo("llama-3.3-70b-versatile") == 50_000


def test_tpd_efectivo_cae_a_catalogo(monkeypatch):
    monkeypatch.setattr(admin_bot, "LIMITE_TOKENS_DIA_OVERRIDE", None)
    assert admin_bot._tpd_efectivo("llama-3.3-70b-versatile") == 100_000


def test_tpd_efectivo_modelo_desconocido_es_none(monkeypatch):
    monkeypatch.setattr(admin_bot, "LIMITE_TOKENS_DIA_OVERRIDE", None)
    assert admin_bot._tpd_efectivo("modelo-inventado") is None


def test_formato_limites_modelo_conocido():
    s = admin_bot._formato_limites("llama-3.3-70b-versatile")
    assert "req/min" in s
    assert "tok/min" in s
    assert "req/día" in s
    assert "tok/día" in s


def test_formato_limites_modelo_desconocido():
    assert "no catalogado" in admin_bot._formato_limites("modelo-x")


def test_roles_esperados_sin_familiar(monkeypatch):
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "")
    assert admin_bot._roles_esperados() == ["aikiu"]


def test_roles_esperados_con_familiar(monkeypatch):
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "abc:def")
    assert admin_bot._roles_esperados() == ["aikiu", "familiar"]


def test_roles_esperados_familiar_placeholder(monkeypatch):
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "PEGA_TU_TOKEN")
    assert admin_bot._roles_esperados() == ["aikiu"]


def test_estado_instancia_combina_peor_estado():
    hbs = {"aikiu": {"last_seen": datetime.now().isoformat()}, "familiar": None}
    # aikiu verde, familiar ausente → peor es ausente
    assert admin_bot._estado_instancia(hbs, ["aikiu", "familiar"]) == "ausente"
    # Si solo aikiu es esperado, verde
    assert admin_bot._estado_instancia(hbs, ["aikiu"]) == "verde"


def test_icono_salud():
    assert admin_bot._icono_salud("ok") == "🟢"
    assert admin_bot._icono_salud("vacio") == "⚪"
    assert admin_bot._icono_salud("corrupto") == "🔴"
    assert admin_bot._icono_salud("falta") == "🟡"
    assert admin_bot._icono_salud("???") == "❓"


def test_contar_familiares(tmp_path):
    (tmp_path / "familiares.json").write_text(
        json.dumps([{"chat_id": 1}, {"chat_id": 2}, {"chat_id": 3}]),
        encoding="utf-8",
    )
    assert admin_bot._contar_familiares(tmp_path) == 3


def test_contar_familiares_sin_archivo(tmp_path):
    assert admin_bot._contar_familiares(tmp_path) == 0


def test_serie_mensajes_7d(tmp_path):
    """Devuelve los últimos 7 días, completando con 0 los faltantes."""
    hoy = datetime.now().date()
    stats = {
        hoy.strftime("%Y-%m-%d"): {"mensajes": 5},
        (hoy - timedelta(days=2)).strftime("%Y-%m-%d"): {"mensajes": 3},
    }
    (tmp_path / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    serie = admin_bot._serie_mensajes_7d(tmp_path)
    assert len(serie) == 7
    assert serie[-1] == 5  # hoy
    assert serie[-3] == 3  # hace 2 días


def test_stats_dias_devuelve_n_dias(tmp_path):
    stats = {
        "2026-05-22": {"mensajes": 5},
        "2026-05-21": {"mensajes": 3},
        "2026-05-20": {"mensajes": 1},
    }
    (tmp_path / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
    dias = admin_bot._stats_dias(tmp_path, 2)
    assert len(dias) == 2
    # Más reciente primero
    assert dias[0][0] == "2026-05-22"


def test_tamano_logs_sin_directorio(tmp_path):
    tam, n = admin_bot._tamano_logs(tmp_path)
    assert tam == 0 and n == 0


def test_tamano_logs_con_archivos(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "2026-05-22.md").write_text("contenido", encoding="utf-8")
    (logs_dir / "2026-05-21.md").write_text("mas", encoding="utf-8")
    tam, n = admin_bot._tamano_logs(tmp_path)
    assert n == 2
    assert tam > 0


def test_salud_archivos_todos_ok(tmp_path):
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "stats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "usage.json").write_text("[]", encoding="utf-8")
    (tmp_path / "familiares.json").write_text("[]", encoding="utf-8")
    (tmp_path / "perfil.md").write_text("# perfil", encoding="utf-8")
    salud = admin_bot._salud_archivos(tmp_path)
    estados = {nombre: estado for nombre, estado, _ in salud}
    assert all(e == "ok" for e in estados.values())


def test_salud_archivos_falta(tmp_path):
    salud = admin_bot._salud_archivos(tmp_path)
    estados = {nombre: estado for nombre, estado, _ in salud}
    assert all(e == "falta" for e in estados.values())


def test_salud_archivos_vacio(tmp_path):
    (tmp_path / "state.json").write_text("", encoding="utf-8")
    salud = dict((n, e) for n, e, _ in admin_bot._salud_archivos(tmp_path))
    assert salud["state.json"] == "vacio"


def test_salud_archivos_json_corrupto(tmp_path):
    (tmp_path / "state.json").write_text("{ no es json", encoding="utf-8")
    salud = dict((n, e) for n, e, _ in admin_bot._salud_archivos(tmp_path))
    assert salud["state.json"] == "corrupto"


def test_resumen_instancia(tmp_path, monkeypatch):
    (tmp_path / "config.yml").write_text("nombre_adulto_mayor: Marta", encoding="utf-8")
    monkeypatch.setattr(admin_bot.hb_mod, "leer_heartbeats",
                        lambda d: {"aikiu": {"x": 1}, "familiar": None})
    res = admin_bot._resumen_instancia(tmp_path)
    assert res["nombre_adulto"] == "Marta"
    assert res["hb_aikiu"] == {"x": 1}


def test_buscar_instancia_existente(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "default")
    assert admin_bot._buscar_instancia("default") == tmp_path


def test_buscar_instancia_inexistente(monkeypatch, tmp_path):
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "x")
    assert admin_bot._buscar_instancia("otro") is None


def test_tail_lineas_sin_archivo(tmp_path):
    assert admin_bot._tail_lineas(tmp_path / "no_existe.log", 10) == []


def test_tail_lineas_devuelve_ultimas(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("\n".join(f"linea {i}" for i in range(50)), encoding="utf-8")
    res = admin_bot._tail_lineas(p, 5)
    assert res[-1] == "linea 49"
    assert len(res) == 5


def test_tail_lineas_filtro_errores(tmp_path):
    p = tmp_path / "x.log"
    p.write_text(
        "\n".join([
            "2026-05-22 [INFO] todo bien",
            "2026-05-22 [WARNING] cuidado",
            "2026-05-22 [INFO] hola",
            "2026-05-22 [ERROR] error grande",
            "2026-05-22 [INFO] mas",
        ]),
        encoding="utf-8",
    )
    res = admin_bot._tail_lineas(p, 10, solo_errores=True)
    assert len(res) == 2
    assert any("WARNING" in l for l in res)
    assert any("ERROR" in l for l in res)


# ---------------------------------------------------------------------------
# cmd_start
# ---------------------------------------------------------------------------

def test_cmd_start_admin_ya_registrado_muestra_menu():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    run(admin_bot.cmd_start(update, ctx))
    update.message.reply_text.assert_awaited_once()
    args = update.message.reply_text.await_args
    assert "Aikiu Admin" in args.args[0]


def test_cmd_start_primer_admin_registra_y_muestra_menu(monkeypatch):
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [Path(".")])
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    run(admin_bot.cmd_start(update, ctx))
    assert admin_state.es_admin(42) is True
    update.message.reply_text.assert_awaited_once()
    assert "primer admin" in update.message.reply_text.await_args.args[0]


def test_cmd_start_segundo_admin_dentro_de_cupo(monkeypatch):
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [])
    admin_state.registrar_admin(1)
    update = _fake_update(chat_id=2)
    ctx = _fake_context()
    run(admin_bot.cmd_start(update, ctx))
    assert admin_state.es_admin(2) is True
    assert "2 de 5" in update.message.reply_text.await_args.args[0]


def test_cmd_start_cupo_lleno_rechaza(monkeypatch):
    for cid in range(1, 6):
        admin_state.registrar_admin(cid)
    update = _fake_update(chat_id=999)
    ctx = _fake_context()
    run(admin_bot.cmd_start(update, ctx))
    # No respondió
    update.message.reply_text.assert_not_awaited()


def test_cmd_start_con_env_override_rechaza(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "1")
    update = _fake_update(chat_id=999)
    ctx = _fake_context()
    run(admin_bot.cmd_start(update, ctx))
    update.message.reply_text.assert_not_awaited()


# ---------------------------------------------------------------------------
# cmd_ayuda
# ---------------------------------------------------------------------------

def test_cmd_ayuda_solo_admins():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_ayuda(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_ayuda_admin_recibe_menu():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_ayuda(update, _fake_context()))
    update.message.reply_text.assert_awaited_once()
    assert "Aikiu Admin" in update.message.reply_text.await_args.args[0]


# ---------------------------------------------------------------------------
# cmd_admins
# ---------------------------------------------------------------------------

def test_cmd_admins_solo_admins():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_admins(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_admins_muestra_lista():
    admin_state.registrar_admin(42)
    admin_state.registrar_admin(99)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_admins(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "42" in msg
    assert "99" in msg
    assert "vos" in msg  # marca al que pregunta


def test_cmd_admins_indica_cupo_disponible():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_admins(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "4 lugar" in msg or "lugar(es)" in msg


def test_cmd_admins_indica_cupo_lleno(monkeypatch):
    for cid in range(1, 6):
        admin_state.registrar_admin(cid)
    update = _fake_update(chat_id=1)
    run(admin_bot.cmd_admins(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Cupo lleno" in msg or "lleno" in msg


def test_cmd_admins_con_env_lock(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_IDS", "42")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_admins(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "ADMIN_CHAT_IDS" in msg or "env" in msg.lower()


# ---------------------------------------------------------------------------
# cmd_quitar_admin
# ---------------------------------------------------------------------------

def test_cmd_quitar_admin_no_admin_rechaza():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["99"])))
    update.message.reply_text.assert_not_awaited()


def test_cmd_quitar_admin_sin_args_muestra_uso():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=[])))
    msg = update.message.reply_text.await_args.args[0]
    assert "/quitar_admin" in msg
    assert "<chat_id>" in msg


def test_cmd_quitar_admin_id_invalido():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["no-numero"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "no es un chat_id" in msg


def test_cmd_quitar_admin_no_existe():
    admin_state.registrar_admin(42)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["999"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "no figura" in msg


def test_cmd_quitar_admin_con_env_no_se_puede(monkeypatch):
    admin_state.registrar_admin(42)
    monkeypatch.setenv("ADMIN_CHAT_IDS", "42,99")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["42"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "env" in msg.lower() or "ADMIN_CHAT_IDS" in msg


def test_cmd_quitar_admin_exitoso():
    admin_state.registrar_admin(42)
    admin_state.registrar_admin(99)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["99"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "Saqué" in msg
    assert admin_state.es_admin(99) is False


def test_cmd_quitar_admin_a_si_mismo_avisa():
    admin_state.registrar_admin(42)
    admin_state.registrar_admin(99)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_quitar_admin(update, _fake_context(args=["42"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "vos mismo" in msg or "vos" in msg


# ---------------------------------------------------------------------------
# cmd_instancias
# ---------------------------------------------------------------------------

def test_cmd_instancias_no_admin():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_instancias(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_instancias_vacio(monkeypatch):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [])
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_instancias(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "No detecté" in msg


def test_cmd_instancias_listado(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "marta")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")
    monkeypatch.setattr(admin_bot.hb_mod, "leer_heartbeats",
                        lambda d: {"aikiu": {"last_seen": datetime.now().isoformat()},
                                   "familiar": None})
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_instancias(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Marta" in msg
    assert "marta" in msg


# ---------------------------------------------------------------------------
# cmd_health
# ---------------------------------------------------------------------------

def test_cmd_health_no_admin():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_health(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_health_todo_ok(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")
    monkeypatch.setattr(admin_bot, "_ping_telegram", AsyncMock(return_value="@aikiu_bot"))
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "")  # solo aikiu esperado
    now_iso = datetime.now().isoformat()
    monkeypatch.setattr(admin_bot.hb_mod, "leer_heartbeats",
                        lambda d: {"aikiu": {"last_seen": now_iso, "started_at": now_iso},
                                   "familiar": None})
    update = _fake_update(chat_id=42)
    ctx = _fake_context()
    run(admin_bot.cmd_health(update, ctx))
    msg = update.message.reply_text.await_args.args[0]
    assert "Health check" in msg
    assert "Marta" in msg


def test_cmd_health_rojo_muestra_tip(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "M")
    monkeypatch.setattr(admin_bot, "_ping_telegram", AsyncMock(return_value=None))
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "")
    monkeypatch.setattr(admin_bot.hb_mod, "leer_heartbeats",
                        lambda d: {"aikiu": None, "familiar": None})
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_health(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Tip" in msg or "start.sh" in msg


# ---------------------------------------------------------------------------
# _ping_telegram
# ---------------------------------------------------------------------------

def test_ping_telegram_sin_token():
    assert run(admin_bot._ping_telegram("")) is None
    assert run(admin_bot._ping_telegram("PEGA_TU_TOKEN")) is None


def test_ping_telegram_exitoso(monkeypatch):
    from telegram import Bot as RealBot
    mock_bot = MagicMock()
    me = MagicMock()
    me.username = "aikiu_test_bot"
    me.first_name = "x"
    mock_bot.get_me = AsyncMock(return_value=me)
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(return_value=mock_bot)
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("admin.bot.Bot", return_value=bot_ctx):
        res = run(admin_bot._ping_telegram("abc:def"))
    assert res == "aikiu_test_bot"


def test_ping_telegram_falla(monkeypatch):
    bot_ctx = MagicMock()
    bot_ctx.__aenter__ = AsyncMock(side_effect=Exception("boom"))
    bot_ctx.__aexit__ = AsyncMock(return_value=False)
    with patch("admin.bot.Bot", return_value=bot_ctx):
        res = run(admin_bot._ping_telegram("abc:def"))
    assert res is None


# ---------------------------------------------------------------------------
# cmd_llm
# ---------------------------------------------------------------------------

def test_cmd_llm_no_admin():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_llm(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_llm_sin_actividad(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")
    # usage_mod responde vacío
    vacio = {"chat": {"total": 0, "ok": 0, "error": 0, "tokens_total": 0, "tokens_in": 0, "tokens_out": 0,
                       "latencias_ms": [], "errores_por_tipo": {}},
             "stt": {"total": 0, "ok": 0, "error": 0, "latencias_ms": [], "bytes_audio": 0, "errores_por_tipo": {}}}
    monkeypatch.setattr(admin_bot.usage_mod, "resumen_simple", lambda d, dias=1: vacio)
    monkeypatch.setattr(admin_bot.usage_mod, "resumir", lambda d, dias=30: {"por_modelo": {}})
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_llm(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Sin actividad" in msg


def test_cmd_llm_con_actividad_y_errores(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")

    def fake_resumen_simple(d, dias=1):
        return {
            "chat": {
                "total": 10, "ok": 8, "error": 2, "tokens_total": 5000,
                "tokens_in": 3000, "tokens_out": 2000, "latencias_ms": [500, 700, 900, 600, 800, 750],
                "errores_por_tipo": {"rate limit (429)": 2},
            },
            "stt": {
                "total": 3, "ok": 3, "error": 0, "latencias_ms": [1000, 1500, 1200],
                "bytes_audio": 50_000, "errores_por_tipo": {},
            },
        }
    monkeypatch.setattr(admin_bot.usage_mod, "resumen_simple", fake_resumen_simple)
    monkeypatch.setattr(admin_bot.usage_mod, "resumir",
                        lambda d, dias=30: {"por_modelo": {"llama-3.3-70b-versatile": {"llamadas": 10, "total_tokens": 5000}}})

    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_llm(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Uso del LLM" in msg
    assert "Marta" in msg
    assert "Whisper" in msg or "Transcripción" in msg
    # Hay errores → menciona los 429 y el aviso de TPM
    assert "429" in msg or "rate limit" in msg.lower()


# ---------------------------------------------------------------------------
# cmd_metricas
# ---------------------------------------------------------------------------

def test_cmd_metricas_no_admin():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_metricas(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_metricas_sin_instancias(monkeypatch):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [])
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_metricas(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "No detecté" in msg


def test_cmd_metricas_renderiza_basico(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    monkeypatch.setattr(admin_bot, "nombre_adulto_de", lambda d: "Marta")
    monkeypatch.setattr(admin_bot, "FAMILIAR_TOKEN", "")
    now_iso = datetime.now().isoformat()
    monkeypatch.setattr(admin_bot.hb_mod, "leer_heartbeats",
                        lambda d: {"aikiu": {"started_at": now_iso, "last_seen": now_iso},
                                   "familiar": None})
    # usage resume vacío
    monkeypatch.setattr(admin_bot.usage_mod, "resumir",
                        lambda d, dias=1: {"total_llamadas": 0, "errores": 0, "por_modelo": {}})
    # Crear archivos para que /metricas no rompa
    (tmp_path / "state.json").write_text("{}", encoding="utf-8")
    (tmp_path / "stats.json").write_text("{}", encoding="utf-8")
    (tmp_path / "usage.json").write_text("[]", encoding="utf-8")
    (tmp_path / "familiares.json").write_text("[]", encoding="utf-8")
    (tmp_path / "perfil.md").write_text("# perfil", encoding="utf-8")

    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_metricas(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "Métricas operativas" in msg
    assert "Procesos" in msg
    assert "Tráfico" in msg


# ---------------------------------------------------------------------------
# cmd_logs
# ---------------------------------------------------------------------------

def test_cmd_logs_no_admin():
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context()))
    update.message.reply_text.assert_not_awaited()


def test_cmd_logs_sin_archivo(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "No existe" in msg


def test_cmd_logs_con_archivo(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    (tmp_path / "aikiu.log").write_text(
        "\n".join(f"2026-05-22 [INFO] linea {i}" for i in range(40)),
        encoding="utf-8",
    )
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context(args=["5"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "linea 39" in msg
    assert "Log de" in msg


def test_cmd_logs_filtro_err(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    (tmp_path / "aikiu.log").write_text(
        "2026-05-22 [INFO] normal\n2026-05-22 [WARNING] cuidado\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context(args=["err"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "WARNING" in msg
    assert "normal" not in msg


def test_cmd_logs_instancia_inexistente(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context(args=["otro_id"])))
    msg = update.message.reply_text.await_args.args[0]
    assert "no encontrada" in msg


def test_cmd_logs_multi_instancia_pide_id(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    d1 = tmp_path / "i1"
    d1.mkdir()
    d2 = tmp_path / "i2"
    d2.mkdir()
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [d1, d2])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: d.name)
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context(args=[])))
    msg = update.message.reply_text.await_args.args[0]
    assert "cuál" in msg or "id" in msg.lower()


def test_cmd_logs_vacio(monkeypatch, tmp_path):
    admin_state.registrar_admin(42)
    (tmp_path / "aikiu.log").write_text("", encoding="utf-8")
    monkeypatch.setattr(admin_bot, "descubrir_instancias", lambda: [tmp_path])
    monkeypatch.setattr(admin_bot, "id_de", lambda d: "i1")
    update = _fake_update(chat_id=42)
    run(admin_bot.cmd_logs(update, _fake_context()))
    msg = update.message.reply_text.await_args.args[0]
    assert "log vacío" in msg or "vacío" in msg
