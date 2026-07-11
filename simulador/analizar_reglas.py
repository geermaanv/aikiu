"""
Analizador de reglas del núcleo (aikiu_core.md) con GLM-5.

Diseño (importante): NO le preguntamos a GLM "¿qué reglas borrarías?" — eso es
introspección sobre su propio comportamiento, poco confiable (el mismo error de
pedirle al conversador que se autotaguee el distress). Le pedimos tareas
VERIFICABLES en las que un LLM sí rinde:
  1. Detectar reglas que se solapan / dicen lo mismo (redundancia).
  2. Clasificar cada regla en una categoría.

El veredicto final NO lo da GLM: da CANDIDATAS. La confirmación es empírica,
sacando las candidatas y corriendo los 8 escenarios (ver GOAL_LOOP.md).

Uso: python simulador/analizar_reglas.py > simulador/triaje_reglas.md
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")


def extraer_reglas(texto: str) -> list[tuple[int, str, str]]:
    """Devuelve [(n, seccion, regla)] numerando cada bullet '- ' del núcleo."""
    reglas = []
    seccion = "(sin sección)"
    n = 0
    for linea in texto.splitlines():
        if linea.startswith("## "):
            seccion = linea[3:].strip()
        elif linea.startswith("- "):
            n += 1
            reglas.append((n, seccion, linea[2:].strip()))
    return reglas


PROMPT = """Sos un analista de prompts. Abajo hay {n} reglas numeradas que forman el "sistema" de un asistente conversacional para adultos mayores (corre sobre GLM-5). El objetivo es adelgazar el conjunto SIN perder comportamiento.

NO opines sobre si "podrías" seguir cada regla — eso no se puede saber sin probar. Hacé solo dos tareas objetivas:

TAREA A — REDUNDANCIA: encontrá grupos de reglas que digan esencialmente lo mismo o se solapen fuertemente. Para cada grupo, listá los números y cuál conviene conservar como representante.

TAREA B — CATEGORÍA: asigná a CADA regla exactamente una categoría:
  SEGURIDAD  = crítica, nunca quitar (no dar consejos médicos, no inventar datos, derivar al médico, temas sensibles)
  ESTILO     = voz/tono específicos de este producto (voseo, oraciones cortas, anti-eco, aperturas)
  DEFAULT    = cortesía o sentido común que un modelo capaz probablemente ya hace sin que se lo digan
  ANDAMIAJE  = parece escrita para corregir un error puntual de un modelo débil; candidata a quitar y testear
  GERONTO    = técnica gerontológica no obvia (validación, reminiscencia, ambigüedad ante confusión)

Formato de salida EXACTO, sin texto extra:

## Redundancias
- [n1, n2, ...] conservar n1 — motivo en 6 palabras

## Categorías
n | CATEGORÍA | motivo en 6 palabras

## Candidatas a quitar y testear
Lista de números (los DEFAULT + ANDAMIAJE + los redundantes no-representantes), separados por coma.

REGLAS:
{reglas}
"""


async def main():
    core = (BASE_DIR / "aikiu_core.md").read_text(encoding="utf-8")
    reglas = extraer_reglas(core)
    listado = "\n".join(f"{n}. [{sec}] {txt}" for n, sec, txt in reglas)
    prompt = PROMPT.format(n=len(reglas), reglas=listado)

    client = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    r = await client.chat.completions.create(
        model="z-ai/glm-5",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=6000,
        temperature=0.2,
        extra_body={"reasoning": {"enabled": False}},
    )
    salida = r.choices[0].message.content or "(vacío)"
    print(f"# Triaje de reglas de aikiu_core.md — GLM-5\n")
    print(f"Total de reglas analizadas: {len(reglas)}\n")
    print(salida)


if __name__ == "__main__":
    asyncio.run(main())
