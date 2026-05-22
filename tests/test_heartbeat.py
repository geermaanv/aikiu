"""Tests para core/heartbeat.py — escritura, lectura y semáforo."""

import asyncio
import json
import os
from datetime import datetime, timedelta

import pytest

from core import heartbeat as hb_mod


@pytest.fixture(autouse=True)
def _aislar_instancia(tmp_path, monkeypatch):
    """Apunta instance_dir() a un tmp_path para no contaminar el repo."""
    monkeypatch.setattr(hb_mod, "instance_dir", lambda: tmp_path)
    monkeypatch.setenv("AIKIU_INSTANCE_ID", "test-inst")
    yield


def test_escribir_snapshot_inicial_crea_archivo(tmp_path):
    async def correr():
        task = hb_mod.iniciar_heartbeat("aikiu", intervalo=3600)
        path = tmp_path / "heartbeat-aikiu.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["role"] == "aikiu"
        assert data["instance_id"] == "test-inst"
        assert data["pid"] == os.getpid()
        assert "last_seen" in data
        assert "started_at" in data
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(correr())


def test_leer_heartbeat_inexistente_es_none(tmp_path):
    assert hb_mod.leer_heartbeat(tmp_path, "aikiu") is None


def test_leer_heartbeats_devuelve_diccionario(tmp_path):
    res = hb_mod.leer_heartbeats(tmp_path)
    assert set(res.keys()) == {"aikiu", "familiar"}
    assert res["aikiu"] is None and res["familiar"] is None


def test_estado_ausente_si_no_hay_heartbeat():
    assert hb_mod.estado(None) == "ausente"
    assert hb_mod.estado({}) == "ausente"
    assert hb_mod.estado({"last_seen": "no-es-fecha"}) == "ausente"


def test_estado_verde_si_es_reciente():
    now = datetime(2026, 5, 22, 15, 0, 0)
    hb = {"last_seen": (now - timedelta(seconds=30)).isoformat()}
    assert hb_mod.estado(hb, now=now) == "verde"


def test_estado_amarillo_entre_90s_y_5min():
    now = datetime(2026, 5, 22, 15, 0, 0)
    hb = {"last_seen": (now - timedelta(seconds=120)).isoformat()}
    assert hb_mod.estado(hb, now=now) == "amarillo"


def test_estado_rojo_si_pasaron_mas_de_5min():
    now = datetime(2026, 5, 22, 15, 0, 0)
    hb = {"last_seen": (now - timedelta(minutes=30)).isoformat()}
    assert hb_mod.estado(hb, now=now) == "rojo"


def test_uptime_segundos_calcula_delta():
    now = datetime(2026, 5, 22, 15, 0, 0)
    hb = {"started_at": (now - timedelta(hours=2, minutes=30)).isoformat()}
    assert hb_mod.uptime_segundos(hb, now=now) == 2 * 3600 + 30 * 60


def test_uptime_segundos_none_si_falta_dato():
    assert hb_mod.uptime_segundos(None) is None
    assert hb_mod.uptime_segundos({}) is None
    assert hb_mod.uptime_segundos({"started_at": "no-es-fecha"}) is None


def test_formato_uptime():
    assert hb_mod.formato_uptime(None) == "—"
    assert hb_mod.formato_uptime(45) == "0m"
    assert hb_mod.formato_uptime(60) == "1m"
    assert hb_mod.formato_uptime(3700) == "1h 1m"
    assert hb_mod.formato_uptime(2 * 86400 + 4 * 3600 + 13 * 60) == "2d 4h 13m"


def test_escritura_atomica_no_deja_tmp(tmp_path):
    async def correr():
        task = hb_mod.iniciar_heartbeat("familiar", intervalo=3600)
        tmps = list(tmp_path.glob(".hb.*"))
        assert tmps == []
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(correr())
