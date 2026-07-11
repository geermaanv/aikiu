"""
Scheduler de iniciativa para Andromarta.

Cada N minutos evalúa si corresponde que Andromarta arranque la conversación
sola. Probabilidad depende de:
- La franja horaria (ver estado.probabilidad_iniciativa).
- Cuánto hace que no habla con Aikiu (más tiempo → más chance).
- Si ya disparó iniciativa hoy y muchas veces, se reduce la probabilidad.

El loop es asíncrono y se acopla al loop de Telethon.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable

from andromarta import estado as estado_mod
from andromarta import memoria as memoria_mod

log = logging.getLogger("andromarta.scheduler")

INTERVALO_CHECK_SEG = 60 * 15  # cada 15 minutos evalúa
SILENCIO_DISPARADOR_SEG = 60 * 60 * 2  # 2 horas sin Aikiu → más ganas de hablar

# Disparador asincrónico que el script principal le pasa al loop. Recibe
# nada y devuelve nada (o awaitable). Lo definimos como Callable explícito.
CallbackIniciativa = Callable[[], Awaitable[None]]


def _debe_disparar() -> tuple[bool, str]:
    """Decide si toca iniciativa ahora. Devuelve (decision, motivo) para logging."""
    estado = estado_mod.cargar_estado()
    prob_base = estado_mod.probabilidad_iniciativa()

    historial = memoria_mod.cargar_historial()
    silencio = memoria_mod.segundos_desde_ultimo_clara(historial)

    # Boost si hace mucho que Aikiu no escribe (Marta se aburre)
    if silencio is not None and silencio > SILENCIO_DISPARADOR_SEG:
        prob = min(0.9, prob_base * 2.5)
        motivo = f"silencio={silencio//3600}h boost"
    else:
        prob = prob_base
        motivo = "rutina"

    # Si ya disparó iniciativa hoy, reducir a la mitad cada vez
    veces_hoy = estado.get("iniciativas_hoy", 0)
    if veces_hoy > 0:
        prob *= (0.5 ** veces_hoy)
        motivo += f" veces_hoy={veces_hoy}"

    dado = random.random()
    decision = dado < prob
    log.debug(f"iniciativa: prob={prob:.3f} dado={dado:.3f} → {decision} ({motivo})")
    return decision, motivo


def _registrar_iniciativa() -> None:
    estado = estado_mod.cargar_estado()
    estado["iniciativas_hoy"] = estado.get("iniciativas_hoy", 0) + 1
    estado_mod.guardar_estado(estado)


async def loop_iniciativa(callback: CallbackIniciativa) -> None:
    """
    Loop infinito: cada INTERVALO_CHECK_SEG evalúa y, si toca, invoca el callback.

    El callback es el que sabe cómo hablar con Telegram (lo provee andromarta.py).
    Se queda en este módulo solo la lógica de "cuándo".
    """
    log.info(f"Iniciativa: loop arrancado (check cada {INTERVALO_CHECK_SEG // 60} min)")
    while True:
        try:
            await asyncio.sleep(INTERVALO_CHECK_SEG)
            decision, motivo = _debe_disparar()
            if decision:
                log.info(f"Iniciativa: disparando ({motivo})")
                _registrar_iniciativa()
                try:
                    await callback()
                except Exception as e:
                    log.warning(f"Iniciativa: callback falló: {e}")
        except asyncio.CancelledError:
            log.info("Iniciativa: loop cancelado")
            break
        except Exception as e:
            log.warning(f"Iniciativa: error en loop: {e}")
