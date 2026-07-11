"""Tests para andromarta/scheduler.py — loop de iniciativa."""

import asyncio
import random
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from andromarta import scheduler as scheduler_mod
from andromarta import estado as estado_mod
from andromarta import memoria as memoria_mod


@pytest.fixture(autouse=True)
def _aislar(tmp_path, monkeypatch):
    # Aislar disco para que cargar_estado / cargar_historial vayan a tmp_path
    monkeypatch.setattr(estado_mod, "ESTADO_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(estado_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(memoria_mod, "MEMORIA_PATH", tmp_path / "memoria.json")
    monkeypatch.setattr(memoria_mod, "DATA_DIR", tmp_path)
    yield


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# _debe_disparar
# ---------------------------------------------------------------------------

def test_debe_disparar_random_alto_no_dispara():
    """Si el dado > prob, decision=False."""
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.1), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=60), \
         patch.object(random, "random", return_value=0.99):
        decision, motivo = scheduler_mod._debe_disparar()
    assert decision is False
    assert "rutina" in motivo


def test_debe_disparar_random_bajo_dispara():
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.5), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=60), \
         patch.object(random, "random", return_value=0.01):
        decision, _ = scheduler_mod._debe_disparar()
    assert decision is True


def test_debe_disparar_silencio_largo_aumenta_prob():
    """2h+ sin Aikiu → prob_base se multiplica por 2.5 (con cap 0.9)."""
    # Estado con animo bajo → prob_base baja; con silencio > 2h se boostea
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.1), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=10_000), \
         patch.object(random, "random", return_value=0.2):
        # Con prob 0.1, no dispararía con dado=0.2; con boost a 0.25, sí.
        decision, motivo = scheduler_mod._debe_disparar()
    assert decision is True
    assert "silencio" in motivo
    assert "boost" in motivo


def test_debe_disparar_silencio_largo_cap_a_09():
    """Aunque prob_base sea alta (0.5 * 2.5 = 1.25), se capa a 0.9."""
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.5), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=99_999), \
         patch.object(random, "random", return_value=0.89):
        decision, _ = scheduler_mod._debe_disparar()
    assert decision is True
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.5), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=99_999), \
         patch.object(random, "random", return_value=0.95):
        decision, _ = scheduler_mod._debe_disparar()
    assert decision is False


def test_debe_disparar_veces_hoy_reduce_prob():
    """Si ya disparó N veces hoy, prob *= 0.5**N."""
    # Sembrar estado con iniciativas_hoy=2
    estado_mod.guardar_estado({
        "fecha": __import__("datetime").date.today().isoformat(),
        "animo": 6, "energia": 6, "sintomas": [], "eventos": [],
        "iniciativas_hoy": 2,
    })
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.4), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=60), \
         patch.object(random, "random", return_value=0.05):
        # prob = 0.4 * 0.5^2 = 0.1 — dado=0.05 < 0.1 → dispara
        decision, motivo = scheduler_mod._debe_disparar()
    assert decision is True
    assert "veces_hoy=2" in motivo


def test_debe_disparar_silencio_none_es_rutina():
    """Sin user en historial, segundos_desde es None → rutina sin boost."""
    with patch.object(scheduler_mod.estado_mod, "probabilidad_iniciativa", return_value=0.3), \
         patch.object(scheduler_mod.memoria_mod, "segundos_desde_ultimo_clara", return_value=None), \
         patch.object(random, "random", return_value=0.1):
        decision, motivo = scheduler_mod._debe_disparar()
    assert decision is True
    assert "rutina" in motivo


# ---------------------------------------------------------------------------
# _registrar_iniciativa
# ---------------------------------------------------------------------------

def test_registrar_iniciativa_suma_contador():
    scheduler_mod._registrar_iniciativa()
    est = estado_mod.cargar_estado()
    assert est.get("iniciativas_hoy") == 1
    scheduler_mod._registrar_iniciativa()
    scheduler_mod._registrar_iniciativa()
    est = estado_mod.cargar_estado()
    assert est.get("iniciativas_hoy") == 3


# ---------------------------------------------------------------------------
# loop_iniciativa
# ---------------------------------------------------------------------------

def test_loop_iniciativa_cancelable():
    """El loop respeta CancelledError y rompe."""
    async def correr():
        callback = AsyncMock()
        # Forzar intervalo super corto y hacer que _debe_disparar diga False
        monkey = patch.object(scheduler_mod, "INTERVALO_CHECK_SEG", 0.01)
        with monkey, patch.object(scheduler_mod, "_debe_disparar", return_value=(False, "test")):
            task = asyncio.create_task(scheduler_mod.loop_iniciativa(callback))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # El callback nunca se llamó porque _debe_disparar era False
        callback.assert_not_called()
    run(correr())


def test_loop_iniciativa_llama_callback_cuando_dispara():
    async def correr():
        callback = AsyncMock()
        with patch.object(scheduler_mod, "INTERVALO_CHECK_SEG", 0.01), \
             patch.object(scheduler_mod, "_debe_disparar", return_value=(True, "test")), \
             patch.object(scheduler_mod, "_registrar_iniciativa") as mock_reg:
            task = asyncio.create_task(scheduler_mod.loop_iniciativa(callback))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Se llamó al menos una vez
        assert callback.await_count >= 1
        assert mock_reg.call_count >= 1
    run(correr())


def test_loop_iniciativa_callback_fail_no_rompe_loop():
    """Si el callback explota, el loop sigue (log + continuar)."""
    async def correr():
        callback = AsyncMock(side_effect=Exception("kaboom"))
        with patch.object(scheduler_mod, "INTERVALO_CHECK_SEG", 0.01), \
             patch.object(scheduler_mod, "_debe_disparar", return_value=(True, "test")), \
             patch.object(scheduler_mod, "_registrar_iniciativa"):
            task = asyncio.create_task(scheduler_mod.loop_iniciativa(callback))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Hubo al menos un intento aunque haya fallado
        assert callback.await_count >= 1
    run(correr())


def test_loop_iniciativa_error_inesperado_no_rompe_loop():
    """Excepciones en el body del loop (no del callback) tampoco lo matan."""
    async def correr():
        n_calls = {"v": 0}
        def debe_disparar_que_explota():
            n_calls["v"] += 1
            if n_calls["v"] == 1:
                raise RuntimeError("oops")
            return (False, "ok")
        with patch.object(scheduler_mod, "INTERVALO_CHECK_SEG", 0.01), \
             patch.object(scheduler_mod, "_debe_disparar", side_effect=lambda: debe_disparar_que_explota()):
            task = asyncio.create_task(scheduler_mod.loop_iniciativa(AsyncMock()))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # Hubo más de una iteración (sobrevivió al primer error)
        assert n_calls["v"] >= 2
    run(correr())
