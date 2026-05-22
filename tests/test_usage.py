"""Tests para core/usage.py — registro, rotación mensual y resumen."""

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from core import usage as usage_mod


def run(coro):
    """Helper para ejecutar coroutines en un loop nuevo (los tests son sync)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


@pytest.fixture
def dir_inst(tmp_path, monkeypatch):
    """Aísla usage en un directorio temporal.

    Patcha tanto el alias en usage_mod como la función original en core.instance,
    así no hay forma de que una entrada de test termine en el usage.json real
    del repo (lo aprendimos por las malas: solo patchear el alias dejaba escapar
    las llamadas que resolvían vía el módulo original).
    """
    from core import instance as inst_mod
    monkeypatch.setattr(usage_mod, "instance_dir", lambda: tmp_path)
    monkeypatch.setattr(inst_mod, "instance_dir", lambda: tmp_path)
    # Resetear el lock por las dudas (cada test crea uno nuevo via run())
    monkeypatch.setattr(usage_mod, "_lock", asyncio.Lock())
    return tmp_path


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def test_registrar_chat_persiste_entrada(dir_inst):
    usage_obj = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    run(usage_mod.registrar_chat("llama-3.3-70b-versatile", usage_obj, 812))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert len(data) == 1
    e = data[0]
    assert e["op"] == "chat"
    assert e["model"] == "llama-3.3-70b-versatile"
    assert e["prompt_tokens"] == 100
    assert e["completion_tokens"] == 50
    assert e["total_tokens"] == 150
    assert e["latencia_ms"] == 812
    assert "ts" in e


def test_registrar_chat_acepta_usage_como_dict(dir_inst):
    run(usage_mod.registrar_chat("modelo", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, 100))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["prompt_tokens"] == 10
    assert data[0]["total_tokens"] == 15


def test_registrar_chat_calcula_total_si_falta(dir_inst):
    usage_obj = SimpleNamespace(prompt_tokens=3, completion_tokens=7)
    run(usage_mod.registrar_chat("modelo", usage_obj, 50))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["total_tokens"] == 10


def test_registrar_chat_tolera_usage_none(dir_inst):
    run(usage_mod.registrar_chat("modelo", None, 50))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["total_tokens"] == 0


def test_registrar_stt_persiste_entrada(dir_inst):
    run(usage_mod.registrar_stt("whisper-large-v3", 1500, bytes_audio=12345))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["op"] == "stt"
    assert data[0]["model"] == "whisper-large-v3"
    assert data[0]["latencia_ms"] == 1500
    assert data[0]["bytes_audio"] == 12345


def test_registrar_error_persiste_entrada(dir_inst):
    run(usage_mod.registrar_error("chat", "modelo", 200, "RateLimitError: too many requests"))
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["op"] == "error"
    assert data[0]["subop"] == "chat"
    assert "RateLimit" in data[0]["error"]


# ---------------------------------------------------------------------------
# Context managers
# ---------------------------------------------------------------------------

def test_timed_chat_registra_al_salir(dir_inst):
    async def trabajo():
        usage_obj = SimpleNamespace(prompt_tokens=5, completion_tokens=3, total_tokens=8)
        async with usage_mod.timed_chat("modelo") as t:
            t.set_usage(usage_obj)
        return True

    assert run(trabajo()) is True
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["op"] == "chat"
    assert data[0]["total_tokens"] == 8
    assert data[0]["latencia_ms"] >= 0


def test_timed_chat_registra_error_y_repropaga(dir_inst):
    async def trabajo():
        async with usage_mod.timed_chat("modelo"):
            raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match="kaboom"):
        run(trabajo())

    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["op"] == "error"
    assert data[0]["subop"] == "chat"


def test_timed_stt_registra_al_salir(dir_inst):
    async def trabajo():
        async with usage_mod.timed_stt("whisper-large-v3", bytes_audio=999):
            await asyncio.sleep(0)

    run(trabajo())
    data = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    assert data[0]["op"] == "stt"
    assert data[0]["bytes_audio"] == 999


# ---------------------------------------------------------------------------
# Rotación mensual
# ---------------------------------------------------------------------------

def test_rotacion_mueve_entradas_de_mes_anterior(dir_inst):
    # Sembrar usage.json con entradas viejas
    viejas = [
        {"ts": "2026-04-15T10:00:00", "op": "chat", "model": "m", "total_tokens": 100, "latencia_ms": 50},
        {"ts": "2026-04-20T10:00:00", "op": "chat", "model": "m", "total_tokens": 200, "latencia_ms": 60},
    ]
    (dir_inst / "usage.json").write_text(json.dumps(viejas), encoding="utf-8")

    # Forzar un "ahora" en mayo: registramos algo y disparamos rotación
    run(usage_mod._append({"op": "chat", "model": "m", "total_tokens": 10, "latencia_ms": 1,
                            "ts": "2026-05-01T10:00:00"}))

    actuales = json.loads((dir_inst / "usage.json").read_text(encoding="utf-8"))
    # Solo deben quedar las del mes actual (las dos entradas que pasamos: el append y... bueno, depende del mes real).
    # Para no acoplarnos al mes real, lo que aseguramos es que las viejas se movieron.
    archivo_abril = dir_inst / "usage.2026-04.json"
    assert archivo_abril.exists()
    movidas = json.loads(archivo_abril.read_text(encoding="utf-8"))
    assert len(movidas) == 2
    assert {e["total_tokens"] for e in movidas} == {100, 200}
    # Y en usage.json no debe estar ninguna de las viejas
    ts_actuales = {e["ts"] for e in actuales}
    assert "2026-04-15T10:00:00" not in ts_actuales
    assert "2026-04-20T10:00:00" not in ts_actuales


# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------

def test_resumir_agrega_por_modelo(dir_inst):
    ahora = datetime.now().replace(microsecond=0)
    entradas = [
        {"ts": (ahora - timedelta(hours=1)).isoformat(), "op": "chat", "model": "llama",
         "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "latencia_ms": 500},
        {"ts": (ahora - timedelta(hours=2)).isoformat(), "op": "chat", "model": "llama",
         "prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280, "latencia_ms": 800},
        {"ts": (ahora - timedelta(hours=3)).isoformat(), "op": "stt", "model": "whisper",
         "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "latencia_ms": 1500},
        {"ts": (ahora - timedelta(hours=4)).isoformat(), "op": "error", "model": "llama",
         "latencia_ms": 100, "error": "x"},
    ]
    (dir_inst / "usage.json").write_text(json.dumps(entradas), encoding="utf-8")

    r = usage_mod.resumir(dir_inst, dias=7)
    assert r["rango_dias"] == 7
    assert r["errores"] == 1
    assert r["total_llamadas"] == 3
    assert "llama" in r["por_modelo"]
    assert "whisper" in r["por_modelo"]
    llama = r["por_modelo"]["llama"]
    assert llama["llamadas"] == 2
    assert llama["prompt_tokens"] == 300
    assert llama["completion_tokens"] == 130
    assert llama["total_tokens"] == 430
    # p50 entre 500 y 800
    assert 500 <= llama["latencia_p50_ms"] <= 800
    assert llama["latencia_p95_ms"] >= llama["latencia_p50_ms"]


def test_resumir_filtra_fuera_de_rango(dir_inst):
    ahora = datetime.now()
    entradas = [
        {"ts": (ahora - timedelta(days=10)).isoformat(), "op": "chat", "model": "m",
         "total_tokens": 999, "prompt_tokens": 0, "completion_tokens": 0, "latencia_ms": 1},
        {"ts": ahora.isoformat(), "op": "chat", "model": "m",
         "total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5, "latencia_ms": 1},
    ]
    (dir_inst / "usage.json").write_text(json.dumps(entradas), encoding="utf-8")
    r = usage_mod.resumir(dir_inst, dias=1)
    assert r["total_llamadas"] == 1
    assert r["por_modelo"]["m"]["total_tokens"] == 10


def test_resumir_combina_archivos_mensuales(dir_inst):
    ahora = datetime.now().replace(microsecond=0)
    mes_anterior = (ahora.replace(day=1) - timedelta(days=1))

    actual = [
        {"ts": ahora.isoformat(), "op": "chat", "model": "m",
         "total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5, "latencia_ms": 1},
    ]
    pasado = [
        {"ts": mes_anterior.isoformat(), "op": "chat", "model": "m",
         "total_tokens": 20, "prompt_tokens": 10, "completion_tokens": 10, "latencia_ms": 1},
    ]
    (dir_inst / "usage.json").write_text(json.dumps(actual), encoding="utf-8")
    archivo_pasado = dir_inst / f"usage.{mes_anterior.year:04d}-{mes_anterior.month:02d}.json"
    archivo_pasado.write_text(json.dumps(pasado), encoding="utf-8")

    r = usage_mod.resumir(dir_inst, dias=60)
    assert r["total_llamadas"] == 2
    assert r["por_modelo"]["m"]["total_tokens"] == 30


def test_resumir_vacio(dir_inst):
    r = usage_mod.resumir(dir_inst, dias=7)
    assert r["total_llamadas"] == 0
    assert r["errores"] == 0
    assert r["por_modelo"] == {}
    assert r["por_dia"] == {}
