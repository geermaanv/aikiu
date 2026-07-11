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
    despedida: bool = False,
) -> str:
    """
    Genera el próximo turno de Andromarta.

    Si `mensaje_de_clara` viene, lo agrega al historial antes de pedir respuesta.
    Si viene None, asume que Andromarta arranca conversación espontáneamente
    (iniciativa) y le pasa al LLM una instrucción extra para que produzca un
    mensaje de apertura natural.

    Si `despedida=True`, le pide al LLM que el mensaje sea un cierre amable
    de la conversación (la usa el bot cuando el ciclo está por llegar al tope
    de turnos). El cierre debe ser natural, sin sonar a despedida formal.
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

    if despedida:
        # Va DESPUÉS del mensaje de Aikiu (o de la instrucción de iniciativa)
        # para que pese más a la hora de generar la respuesta.
        messages.append({
            "role": "system",
            "content": (
                "Esta es la ÚLTIMA respuesta tuya en este rato de charla: ya "
                "venís hablando hace un buen tiempo y querés cerrar para volver "
                "a tus cosas. Despedite de forma natural y breve (1 o 2 oraciones), "
                "como una persona mayor que dice 'bueno mi vida, te dejo que "
                "tengo que poner la pava' o 'me voy a recostar un ratito, "
                "hablamos más tarde'. Variá la excusa según tu estado de hoy "
                "(cansancio, una visita, ir al kiosco, la novela en la tele, "
                "atender el teléfono). No suenes formal ni hagas resumen del "
                "rato que hablaron. NO digas 'chau' tipo despedida final ni "
                "des a entender que no van a hablar más; es solo un 'te dejo "
                "por ahora'. Después de este mensaje, vos NO vas a responder "
                f"nada más hasta que se te ocurra a vos volver a escribirle a "
                f"{nombre_clara}."
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
    log.info(f"Andromarta dice{' [despedida]' if despedida else ''}: '{limpio}'")
    return limpio
