"""
Generador de mensajes de Andromarta — pega persona + estado + memoria y llama a Groq.

Devuelve siempre texto plano (sin DISTRESS_LEVEL ni metadata). El llamador
decide si lo manda como texto o como nota de voz vía edge-tts.
"""

from __future__ import annotations

import logging
import re

from groq import AsyncGroq

from andromarta import estado as estado_mod
from andromarta import memoria as memoria_mod
from andromarta.persona import construir_system_prompt, leer_perfil

log = logging.getLogger("andromarta.generador")


def _limpiar_artefactos(texto: str) -> str:
    """Saca cosas que el LLM puede meter sin querer (DISTRESS_LEVEL, comillas, etc)."""
    texto = re.sub(r"DISTRESS_LEVEL:\s*\d+", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\*+", "", texto)  # asteriscos de markdown
    texto = texto.strip()
    if (texto.startswith('"') and texto.endswith('"')) or (
        texto.startswith("'") and texto.endswith("'")
    ):
        texto = texto[1:-1].strip()
    return texto


async def responder(
    groq: AsyncGroq,
    modelo: str,
    historial: list[dict],
    nombre_clara: str,
    mensaje_de_clara: str | None = None,
) -> str:
    """
    Genera el próximo turno de Andromarta.

    Si `mensaje_de_clara` viene, lo agrega al historial antes de pedir respuesta.
    Si viene None, asume que Andromarta arranca conversación espontáneamente
    (iniciativa) y le pasa al LLM una instrucción extra para que produzca un
    mensaje de apertura natural.
    """
    estado = estado_mod.cargar_estado()
    perfil = leer_perfil()
    estado_humano = estado_mod.descripcion_humana(estado)
    system_prompt = construir_system_prompt(perfil, estado_humano, nombre_clara)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    messages.extend(memoria_mod.ventana_para_llm(historial))

    if mensaje_de_clara is not None:
        messages.append({"role": "user", "content": mensaje_de_clara})
    else:
        # Iniciativa: instrucción extra para que arranque conversación
        franja = estado_mod.hora_del_dia()
        messages.append({
            "role": "system",
            "content": (
                f"En este turno NO hay mensaje de {nombre_clara} pendiente: vos "
                f"arrancás la conversación espontáneamente. Estamos en la {franja}. "
                f"Mandá un mensaje natural y corto (1 o 2 oraciones), como cuando "
                f"alguien manda un 'che' por whatsapp. Puede ser un saludo, contar "
                f"algo del día, una duda, una observación del clima. No saludes con "
                f"'¿Cómo estás?' siempre — variá. Si ya hablaron hace poco, no "
                f"hagas como que recién aparecés: continuá natural."
            ),
        })

    response = await groq.chat.completions.create(
        model=modelo,
        messages=messages,
        max_tokens=180,
        temperature=0.9,  # más alto que Aikiu: queremos variedad humana
    )
    raw = response.choices[0].message.content.strip()
    limpio = _limpiar_artefactos(raw)
    log.info(f"Andromarta dice: '{limpio}'")
    return limpio
