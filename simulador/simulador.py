"""
Simulador de conversación Aikiu.
Agente A (Gemini): simula al adulto mayor usando una persona .md
Agente B (cascada): Groq → Gemini → OpenRouter según disponibilidad

No toca perfil.md de producción.
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from groq import AsyncGroq

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.environ.get("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

PERFIL_SIM_PATH = BASE_DIR / "simulador" / "perfil_simulacion.md"
LOGS_SIM_DIR    = BASE_DIR / "simulador" / "logs"

# Modelos en orden de preferencia (proveedor, model_id)
BOT_BACKENDS = [
    ("groq",       "llama-3.3-70b-versatile"),
    ("gemini",     "gemini-2.5-flash"),
    ("openrouter", "openai/gpt-oss-120b:free"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
]


def cargar_persona(nombre: str = "marta") -> str:
    path = BASE_DIR / "simulador" / "personas" / f"{nombre}.md"
    contenido = path.read_text(encoding="utf-8")
    return f"Actuá exactamente según este perfil:\n\n{contenido}\n\nSé realista. No rompas el personaje."


def cargar_perfil_simulacion() -> str:
    if PERFIL_SIM_PATH.exists():
        return PERFIL_SIM_PATH.read_text(encoding="utf-8")
    perfil_prod = BASE_DIR / "perfil.md"
    contenido = perfil_prod.read_text(encoding="utf-8")
    PERFIL_SIM_PATH.write_text(contenido, encoding="utf-8")
    print("[simulador] perfil_simulacion.md creado desde perfil.md")
    return contenido


def system_prompt_bot(perfil: str, core: str = "", nombre_adulto: str = "Marta", nombre_bot: str = "Clara") -> str:
    sys.path.insert(0, str(BASE_DIR))
    from core.utils import fecha_hora_es
    partes = [f"Tu nombre es {nombre_bot}. Hablás con {nombre_adulto}.\n"]
    if core:
        partes.append(f"## LINEAMIENTOS DEL SISTEMA\n{core}\n")
    partes.append(f"## PERFIL DE {nombre_adulto.upper()}\n{perfil}\n")
    partes.append(
        f"Fecha y hora actual: {fecha_hora_es()} (hora de Buenos Aires).\n"
        f"Respondé siempre en español rioplatense. Máximo 3 oraciones. "
        f"Nunca uses markdown. Al final de cada respuesta agregá: DISTRESS_LEVEL: 0"
    )
    return "".join(partes)


async def _llamar_bot(
    proveedor: str,
    model: str,
    messages: list[dict],
    gemini_client: genai.Client,
) -> str:
    """Llama al backend indicado y devuelve el texto generado."""
    if proveedor == "groq":
        client = AsyncGroq(api_key=GROQ_API_KEY)
        r = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        return r.choices[0].message.content.strip()

    if proveedor == "gemini":
        # Gemini no tiene API OpenAI-compatible en genai SDK, usamos generate_content
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        historia = [m for m in messages if m["role"] != "system"]
        # Convertir historial a formato Gemini
        contents = []
        for m in historia:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        resp = gemini_client.models.generate_content(
            model=model,
            contents=contents,
            config={"system_instruction": system, "max_output_tokens": 200},
        )
        return resp.text.strip()

    if proveedor == "openrouter":
        # OpenRouter es compatible con la API de OpenAI
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
        )
        r = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        return r.choices[0].message.content.strip()

    raise ValueError(f"Proveedor desconocido: {proveedor}")


async def llamar_bot_con_fallback(
    messages: list[dict],
    gemini_client: genai.Client,
) -> tuple[str, str]:
    """Intenta cada backend en orden; devuelve (texto, proveedor_usado)."""
    ultimo_error = None
    for proveedor, model in BOT_BACKENDS:
        # Saltar si no hay API key
        if proveedor == "groq" and not GROQ_API_KEY:
            continue
        if proveedor == "gemini" and not GEMINI_API_KEY:
            continue
        if proveedor == "openrouter" and not OPENROUTER_API_KEY:
            continue
        try:
            texto = await _llamar_bot(proveedor, model, messages, gemini_client)
            return texto, proveedor
        except Exception as e:
            msg = str(e)
            # 429 o cuota agotada → intentar siguiente
            if "429" in msg or "rate_limit" in msg.lower() or "quota" in msg.lower() or "unavailable" in msg.lower():
                print(f"[simulador] {proveedor} no disponible ({msg[:80]}...) → intentando siguiente")
                ultimo_error = e
                continue
            raise  # error distinto → propagar
    raise RuntimeError(f"Todos los backends fallaron. Último error: {ultimo_error}")


async def simular(
    persona: str = "marta",
    turnos: int = 10,
    iteracion: int = 1,
) -> tuple[list[dict], Path]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")

    perfil = cargar_perfil_simulacion()
    persona_prompt = cargar_persona(persona)

    # Cargar lineamientos del sistema (aikiu_core.md)
    core_path = BASE_DIR / "aikiu_core.md"
    core = core_path.read_text(encoding="utf-8") if core_path.exists() else ""

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    # Agente A: Gemini simula al adulto mayor
    chat_usuario = gemini_client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": persona_prompt},
    )

    # Agente B: bot con fallback multi-proveedor
    historial_bot: list[dict] = []
    sp_bot = system_prompt_bot(perfil, core)

    LOGS_SIM_DIR.mkdir(exist_ok=True)
    log_path = LOGS_SIM_DIR / f"iter{iteracion:02d}_{persona}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    conversacion = []
    backend_actual = "?"

    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  Simulación — Iteración {iteracion} | Persona: {persona} | {turnos} turnos")
    print(f"{sep}\n")

    resp_usuario = chat_usuario.send_message("Iniciá la conversación como lo haría tu personaje.")
    msg_usuario  = resp_usuario.text.strip()

    for turno in range(turnos):
        print(f"[{persona.capitalize()}]: {msg_usuario}\n")

        historial_bot.append({"role": "user", "content": msg_usuario})
        messages = [{"role": "system", "content": sp_bot}] + historial_bot[-20:]

        msg_bot, backend_actual = await llamar_bot_con_fallback(messages, gemini_client)

        msg_bot_limpio = "\n".join(
            l for l in msg_bot.splitlines() if not l.startswith("DISTRESS_LEVEL")
        ).strip()
        historial_bot.append({"role": "assistant", "content": msg_bot_limpio})

        print(f"[Clara ({backend_actual})]:   {msg_bot_limpio}\n")
        print("─" * 40)

        conversacion.append({
            "turno": turno + 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "usuario": msg_usuario,
            "bot": msg_bot_limpio,
            "backend": backend_actual,
        })

        if turno < turnos - 1:
            resp_usuario = chat_usuario.send_message(msg_bot_limpio)
            msg_usuario  = resp_usuario.text.strip()

    with open(log_path, "w", encoding="utf-8") as f:
        for entry in conversacion:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n[simulador] Log guardado: {log_path.name} (backend final: {backend_actual})")
    return conversacion, log_path


if __name__ == "__main__":
    persona  = sys.argv[1] if len(sys.argv) > 1 else "marta"
    turnos   = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    asyncio.run(simular(persona=persona, turnos=turnos))
