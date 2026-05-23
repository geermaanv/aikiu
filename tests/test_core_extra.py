"""Tests extra para core/* — cubre las brechas de alerts, heartbeat, tools,
tts, usage y state que no estaban cubiertas por suites previas."""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# core/alerts.py — notify_family
# ---------------------------------------------------------------------------

def test_distress_messages_estructura():
    from core.alerts import _distress_messages
    msgs = _distress_messages("Marta")
    assert 1 in msgs and 2 in msgs and 3 in msgs
    assert "Marta" in msgs[1]
    assert "Marta" in msgs[2]
    assert "Marta" in msgs[3]


def test_cargar_suscriptores_sin_archivo(tmp_path, monkeypatch):
    from core import alerts
    monkeypatch.setattr(alerts, "FAMILIARES_PATH", tmp_path / "no.json")
    assert alerts.cargar_suscriptores() == []


def test_cargar_suscriptores_con_archivo(tmp_path, monkeypatch):
    from core import alerts
    (tmp_path / "fam.json").write_text(
        json.dumps([{"chat_id": 1}, {"chat_id": 2}, {"chat_id": 3}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(alerts, "FAMILIARES_PATH", tmp_path / "fam.json")
    assert alerts.cargar_suscriptores() == [1, 2, 3]


def test_notify_family_sin_suscriptores_no_envia(monkeypatch):
    from core import alerts
    monkeypatch.setattr(alerts, "cargar_suscriptores", lambda *a, **k: [])
    bot = MagicMock()
    bot.send_message = AsyncMock()
    run(alerts.notify_family(1, "msg", "resp", bot))
    bot.send_message.assert_not_awaited()


def test_notify_family_envia_a_todos(monkeypatch):
    from core import alerts
    monkeypatch.setattr(alerts, "cargar_suscriptores", lambda *a, **k: [10, 20, 30])
    bot = MagicMock()
    bot.send_message = AsyncMock()
    run(alerts.notify_family(2, "me siento mal", "te acompaño", bot))
    assert bot.send_message.await_count == 3
    args = bot.send_message.await_args
    assert args.kwargs["chat_id"] in (10, 20, 30)
    assert args.kwargs["parse_mode"] == "Markdown"


def test_notify_family_un_envio_falla_y_sigue(monkeypatch):
    from core import alerts
    monkeypatch.setattr(alerts, "cargar_suscriptores", lambda *a, **k: [10, 20])
    bot = MagicMock()
    enviados = []
    async def fake_send(**kwargs):
        if kwargs["chat_id"] == 10:
            raise Exception("user blocked")
        enviados.append(kwargs["chat_id"])
    bot.send_message = fake_send
    run(alerts.notify_family(3, "x", "y", bot))
    assert enviados == [20]


def test_notify_family_nivel_3_es_alerta_roja(monkeypatch):
    from core import alerts
    monkeypatch.setattr(alerts, "cargar_suscriptores", lambda *a, **k: [1])
    mensajes = []
    bot = MagicMock()
    async def fake_send(**kwargs):
        mensajes.append(kwargs["text"])
    bot.send_message = fake_send
    run(alerts.notify_family(3, "ayuda", "llamando médico", bot))
    assert "ALERTA" in mensajes[0] or "🔴" in mensajes[0]


def test_notify_family_un_envio_falla_y_loggea(monkeypatch):
    """Verifica que un fallo individual no rompe el batch."""
    from core import alerts
    monkeypatch.setattr(alerts, "cargar_suscriptores", lambda *a, **k: [10])
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=Exception("Forbidden"))
    # No debe lanzar
    run(alerts.notify_family(1, "x", "y", bot))


# ---------------------------------------------------------------------------
# core/heartbeat.py — _escribir_atomico, _loop, errores
# ---------------------------------------------------------------------------

def test_heartbeat_escribir_atomico_falla_borra_tmp(tmp_path):
    """Si json.dump falla, el tmp se borra."""
    from core import heartbeat as hb
    path = tmp_path / "x.json"
    obj_no_serializable = {"x": object()}  # objects no son serializable
    with pytest.raises(TypeError):
        hb._escribir_atomico(path, obj_no_serializable)
    # No quedaron tmps
    assert not list(tmp_path.glob(".hb.*"))


def test_heartbeat_leer_json_corrupto(tmp_path):
    from core import heartbeat as hb
    (tmp_path / "heartbeat-aikiu.json").write_text("{ no es json", encoding="utf-8")
    assert hb.leer_heartbeat(tmp_path, "aikiu") is None


def test_heartbeat_loop_logea_error_y_sigue(tmp_path, monkeypatch):
    """Si _escribir_atomico falla, el loop loggea y sigue al siguiente intervalo."""
    from core import heartbeat as hb
    monkeypatch.setattr(hb, "instance_dir", lambda: tmp_path)

    async def correr():
        with patch.object(hb, "_escribir_atomico", side_effect=RuntimeError("disk full")):
            task = hb.iniciar_heartbeat("aikiu", intervalo=0)
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    run(correr())


def test_heartbeat_snapshot_role_admin(tmp_path, monkeypatch):
    """El snapshot para role=admin usa admin_state.admin_chat_id()."""
    from core import heartbeat as hb
    from admin import state as adm
    monkeypatch.setattr(adm, "ADMIN_STATE_PATH", tmp_path / "x.json")
    adm.registrar_admin(777)
    snap = hb._snapshot("admin", "2026-05-22T10:00:00")
    assert snap["owner_chat_id"] == 777
    assert snap["role"] == "admin"


def test_heartbeat_snapshot_role_familiar_owner_none():
    from core import heartbeat as hb
    snap = hb._snapshot("familiar", "2026-05-22T10:00:00")
    assert snap["owner_chat_id"] is None
    assert snap["role"] == "familiar"


def test_heartbeat_snapshot_role_desconocido_owner_none():
    from core import heartbeat as hb
    snap = hb._snapshot("xxx", "2026-05-22T10:00:00")
    assert snap["owner_chat_id"] is None


def test_heartbeat_iniciar_con_dir_override(tmp_path, monkeypatch):
    from core import heartbeat as hb
    async def correr():
        dir_override = tmp_path / "admin_dir"
        dir_override.mkdir()
        task = hb.iniciar_heartbeat("admin", intervalo=3600, dir_override=dir_override)
        # Se escribió en dir_override
        assert (dir_override / "heartbeat-admin.json").exists()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    run(correr())


def test_heartbeat_iniciar_snapshot_inicial_falla_no_rompe(tmp_path, monkeypatch):
    """Si el snapshot inicial falla, igual arranca el loop."""
    from core import heartbeat as hb
    monkeypatch.setattr(hb, "instance_dir", lambda: tmp_path)

    async def correr():
        with patch.object(hb, "_escribir_atomico", side_effect=RuntimeError("kaboom")):
            task = hb.iniciar_heartbeat("aikiu", intervalo=3600)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    run(correr())


def test_heartbeat_estado_last_seen_invalido():
    from core import heartbeat as hb
    assert hb.estado({"last_seen": "no-fecha"}) == "ausente"


def test_heartbeat_uptime_started_invalido():
    from core import heartbeat as hb
    assert hb.uptime_segundos({"started_at": "no-fecha"}) is None


def test_heartbeat_formato_uptime_negativo():
    from core import heartbeat as hb
    assert hb.formato_uptime(-100) == "—"


# ---------------------------------------------------------------------------
# core/state.py — atomic write
# ---------------------------------------------------------------------------

def test_state_escritura_atomica_borra_tmp_si_falla(tmp_path, monkeypatch):
    from core import state as st
    monkeypatch.setattr(st, "STATE_PATH", tmp_path / "state.json")
    obj_no_serializable = {"x": object()}
    with pytest.raises(TypeError):
        st._escribir_estado_atomico(obj_no_serializable)
    assert not list(tmp_path.glob(".state.*"))


def test_state_owner_chat_id_string_numerico_se_convierte(tmp_path, monkeypatch):
    """Si por alguna razón el JSON tiene el id como string numérico, lo acepta."""
    from core import state as st
    monkeypatch.setattr(st, "STATE_PATH", tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"owner_chat_id": "12345"}), encoding="utf-8")
    monkeypatch.delenv("CHAT_ID", raising=False)
    assert st.owner_chat_id() == 12345


def test_state_owner_chat_id_string_no_numerico_es_none(tmp_path, monkeypatch):
    from core import state as st
    monkeypatch.setattr(st, "STATE_PATH", tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"owner_chat_id": "xxx"}), encoding="utf-8")
    monkeypatch.delenv("CHAT_ID", raising=False)
    assert st.owner_chat_id() is None


def test_state_registrar_owner_segundo_intento_devuelve_false(tmp_path, monkeypatch):
    """Si ya hay un owner registrado (no-None), no se sobreescribe."""
    from core import state as st
    monkeypatch.setattr(st, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.delenv("CHAT_ID", raising=False)
    st.registrar_owner(42)
    assert st.registrar_owner(99) is False
    assert st.owner_chat_id() == 42


# ---------------------------------------------------------------------------
# core/tools.py — paths exitosos
# ---------------------------------------------------------------------------

def _mock_wttr(temp_c, feels_c, desc="Sunny", hum="50"):
    data = {
        "current_condition": [{
            "temp_C": str(temp_c),
            "FeelsLikeC": str(feels_c),
            "weatherDesc": [{"value": desc}],
            "humidity": str(hum),
        }]
    }
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    client = AsyncMock()
    client.__aenter__.return_value.get = AsyncMock(return_value=resp)
    return client


def test_consultar_clima_exitoso():
    from core.tools import consultar_clima
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_wttr(18, 16)):
        res = run(consultar_clima("Buenos Aires"))
    assert "18" in res
    assert "16" in res
    assert "Buenos Aires" in res


def test_consultar_clima_con_ciudad_con_espacios():
    from core.tools import consultar_clima
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_wttr(20, 19)):
        res = run(consultar_clima("Mar del Plata"))
    assert "Mar del Plata" in res


def _mock_dolar(blue=(900, 950), oficial=(750, 800)):
    rb = MagicMock()
    rb.json.return_value = {"compra": blue[0], "venta": blue[1]}
    rb.raise_for_status = MagicMock()
    ro = MagicMock()
    ro.json.return_value = {"compra": oficial[0], "venta": oficial[1]}
    ro.raise_for_status = MagicMock()
    client = AsyncMock()
    client.__aenter__.return_value.get = AsyncMock(side_effect=[rb, ro])
    return client


def test_consultar_dolar_exitoso():
    from core.tools import consultar_dolar
    with patch("core.tools.httpx.AsyncClient", return_value=_mock_dolar()):
        res = run(consultar_dolar())
    assert "Blue" in res
    assert "900" in res
    assert "Oficial" in res


# ---------------------------------------------------------------------------
# core/tts.py — sintetizar (mockeando edge_tts y ffmpeg)
# ---------------------------------------------------------------------------

def test_sintetizar_invoca_edge_tts_y_ffmpeg(tmp_path):
    from core import tts
    salida = tmp_path / "out.ogg"

    fake_communicate = MagicMock()
    fake_communicate.save = AsyncMock()
    fake_proc = MagicMock()
    fake_proc.wait = AsyncMock(return_value=0)

    with patch.object(tts, "edge_tts") as fake_edge, \
         patch("asyncio.create_subprocess_exec", AsyncMock(return_value=fake_proc)) as mock_exec:
        fake_edge.Communicate = MagicMock(return_value=fake_communicate)
        run(tts.sintetizar("hola che", salida, voz="es-AR-X"))
    fake_communicate.save.assert_awaited_once()
    mock_exec.assert_awaited_once()


# ---------------------------------------------------------------------------
# core/usage.py — branches sin cubrir
# ---------------------------------------------------------------------------

def test_usage_leer_archivo_corrupto_devuelve_lista_vacia(tmp_path):
    from core import usage
    p = tmp_path / "u.json"
    p.write_text("{ no es json", encoding="utf-8")
    assert usage._leer(p) == []


def test_usage_leer_archivo_que_no_es_lista(tmp_path):
    """Si es JSON pero no es lista (p.ej. dict), devuelve []."""
    from core import usage
    p = tmp_path / "u.json"
    p.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert usage._leer(p) == []


def test_usage_escritura_atomica_falla_borra_tmp(tmp_path):
    from core import usage
    p = tmp_path / "u.json"
    with pytest.raises(TypeError):
        usage._escribir_atomico(p, [{"x": object()}])
    assert not list(tmp_path.glob(".usage.*"))


def test_usage_rotar_ts_invalido_lo_deja_en_actuales(tmp_path):
    from core import usage
    p = tmp_path / "u.json"
    entradas = [
        {"ts": "no-fecha", "op": "chat", "model": "m", "total_tokens": 1, "latencia_ms": 1},
    ]
    p.write_text(json.dumps(entradas), encoding="utf-8")
    actuales = usage._rotar_si_corresponde(p, datetime.now())
    assert len(actuales) == 1
    # No se generó archivo mensual
    assert not list(tmp_path.glob("usage.*.json"))


def test_usage_clasificar_error_rate_limit():
    from core import usage
    assert usage._clasificar_error("RateLimitError: too many") == "rate limit (429)"
    assert usage._clasificar_error("429 Too Many") == "rate limit (429)"


def test_usage_clasificar_error_timeout():
    from core import usage
    assert usage._clasificar_error("ReadTimeout: slow") == "timeout"


def test_usage_clasificar_error_auth():
    from core import usage
    assert usage._clasificar_error("Invalid API key") == "auth (401)"
    assert usage._clasificar_error("401 Unauthorized") == "auth (401)"


def test_usage_clasificar_error_503():
    from core import usage
    assert usage._clasificar_error("Service Unavailable 503") == "server (503)"


def test_usage_clasificar_error_500():
    from core import usage
    assert usage._clasificar_error("Internal Server Error") == "server (500)"


def test_usage_clasificar_error_conexion():
    from core import usage
    assert usage._clasificar_error("Connection reset") == "conexión"


def test_usage_clasificar_error_otro():
    from core import usage
    assert usage._clasificar_error("Random fail") == "otro"


def test_usage_clasificar_error_vacio():
    from core import usage
    assert usage._clasificar_error("") == "otro"
    assert usage._clasificar_error(None) == "otro"


def test_usage_resumen_simple_completo(tmp_path):
    from core import usage
    ahora = datetime.now()
    entradas = [
        # 2 chat ok
        {"ts": ahora.isoformat(), "op": "chat", "model": "m",
         "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "latencia_ms": 500},
        {"ts": ahora.isoformat(), "op": "chat", "model": "m",
         "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "latencia_ms": 700},
        # 1 stt ok
        {"ts": ahora.isoformat(), "op": "stt", "model": "w",
         "latencia_ms": 1500, "bytes_audio": 5000},
        # 1 error chat
        {"ts": ahora.isoformat(), "op": "error", "subop": "chat",
         "model": "m", "latencia_ms": 100, "error": "RateLimitError"},
        # 1 error stt
        {"ts": ahora.isoformat(), "op": "error", "subop": "stt",
         "model": "w", "latencia_ms": 200, "error": "timeout"},
    ]
    (tmp_path / "usage.json").write_text(json.dumps(entradas), encoding="utf-8")
    r = usage.resumen_simple(tmp_path, dias=1)
    assert r["chat"]["ok"] == 2
    assert r["chat"]["error"] == 1
    assert r["chat"]["total"] == 3
    assert r["chat"]["tokens_total"] == 45
    assert "rate limit (429)" in r["chat"]["errores_por_tipo"]
    assert r["stt"]["ok"] == 1
    assert r["stt"]["error"] == 1
    assert r["stt"]["bytes_audio"] == 5000


def test_usage_resumen_simple_vacio(tmp_path):
    from core import usage
    r = usage.resumen_simple(tmp_path, dias=1)
    assert r["chat"]["total"] == 0
    assert r["stt"]["total"] == 0


def test_usage_cargar_rango_combina_actual_y_mensual(tmp_path):
    from core import usage
    ahora = datetime.now()
    mes_pasado = (ahora.replace(day=1) - timedelta(days=1))
    # Archivo del mes pasado
    archivo_pasado = tmp_path / f"usage.{mes_pasado.year:04d}-{mes_pasado.month:02d}.json"
    archivo_pasado.write_text(json.dumps([
        {"ts": mes_pasado.isoformat(), "op": "chat", "model": "m", "total_tokens": 10},
    ]), encoding="utf-8")
    # Archivo actual
    (tmp_path / "usage.json").write_text(json.dumps([
        {"ts": ahora.isoformat(), "op": "chat", "model": "m", "total_tokens": 20},
    ]), encoding="utf-8")
    rango = usage.cargar_rango(tmp_path, mes_pasado - timedelta(days=1), ahora + timedelta(days=1))
    assert len(rango) == 2


def test_usage_cargar_rango_filtra_ts_invalidos(tmp_path):
    from core import usage
    (tmp_path / "usage.json").write_text(json.dumps([
        {"ts": "no-fecha", "op": "chat", "model": "m", "total_tokens": 1},
        {"ts": datetime.now().isoformat(), "op": "chat", "model": "m", "total_tokens": 2},
    ]), encoding="utf-8")
    rango = usage.cargar_rango(tmp_path, datetime.now() - timedelta(days=1))
    assert len(rango) == 1


def test_usage_percentil_vacio():
    from core import usage
    assert usage._percentil([], 0.5) == 0.0


def test_usage_percentil_calculado():
    from core import usage
    res = usage._percentil([10, 20, 30, 40, 50], 0.5)
    assert res == 30  # p50 de 5 valores impares es el del medio


def test_usage_attr_dict():
    from core import usage
    assert usage._attr({"x": 5}, "x", 0) == 5
    assert usage._attr({}, "x", 99) == 99


def test_usage_attr_objeto():
    from core import usage
    class Obj:
        x = 7
    assert usage._attr(Obj(), "x", 0) == 7
    assert usage._attr(Obj(), "missing", 42) == 42


def test_usage_attr_none():
    from core import usage
    assert usage._attr(None, "x", 99) == 99


def test_usage_rotar_actuales_ts_falta(tmp_path):
    """Una entrada sin 'ts' válido se queda en 'actuales'."""
    from core import usage
    p = tmp_path / "u.json"
    entradas = [{"op": "chat", "model": "m", "total_tokens": 1, "latencia_ms": 1}]
    p.write_text(json.dumps(entradas), encoding="utf-8")
    actuales = usage._rotar_si_corresponde(p, datetime.now())
    assert len(actuales) == 1
