"""
Simulador de conversación Aikiu.
Agente A (Gemini): simula al adulto mayor usando una persona .md
Agente B (cascada): Groq → Gemini → OpenRouter según disponibilidad

No toca perfil.md de producción.
"""

import asyncio
import json
import os
import re
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
ESCENARIOS_PATH = BASE_DIR / "simulador" / "escenarios.json"

# Tolera "DISTRESS_LEVEL: 1", "DISTRESS_LEVEL: [1]" e inline al final de oración.
# Solo se usa para limpiar restos que el conversador pudiera emitir; la
# clasificación real la hace el vigía (parse_distress_classification).
_DISTRESS_RE = re.compile(r"\s*DISTRESS_LEVEL:\s*\[?([0-3])\]?\s*")

sys.path.insert(0, str(BASE_DIR))
from core.distress import parse_distress_classification, _NIVEL_RE


def cargar_escenario(clave: str) -> dict:
    """Devuelve el escenario {nombre, consigna, chequeos} de escenarios.json."""
    data = json.loads(ESCENARIOS_PATH.read_text(encoding="utf-8"))
    if clave not in data:
        raise KeyError(f"Escenario '{clave}' no existe. Disponibles: {', '.join(data)}")
    return data[clave]

# Modelos en orden de preferencia (proveedor, model_id)
# Fase GLM: z-ai/glm-5 (OpenRouter) es el modelo bajo prueba para Aikiu;
# el resto queda como fallback si OpenRouter no responde.
BOT_BACKENDS = [
    ("openrouter", "z-ai/glm-5"),
    ("groq",       "llama-3.3-70b-versatile"),
    ("gemini",     "gemini-2.5-flash"),
    ("openrouter", "openai/gpt-oss-120b:free"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
]

# Override sin tocar código (para A/B): SIM_BOT_MODEL="proveedor:model_id"
# ej. SIM_BOT_MODEL="openrouter:z-ai/glm-4.7" o SIM_BOT_MODEL="groq:llama-3.3-70b-versatile"
_override = os.environ.get("SIM_BOT_MODEL", "")
if ":" in _override:
    _prov, _mod = _override.split(":", 1)
    BOT_BACKENDS.insert(0, (_prov, _mod))


# chat_id reservado para el simulador. Es un hogar real (pasa por toda la
# maquinaria de producción) pero aislado de los hogares de verdad.
HOGAR_SIM = 990001

# Metadatos de la persona, en un comentario al inicio del .md:
#   <!-- ciudad: Buenos Aires, Argentina | genero: F -->
# Sirven para armar el hogar de prueba igual que uno real. Si faltan, se usan
# los defaults.
_META_RE = re.compile(r"<!--\s*(.*?)\s*-->", re.S)


def _meta_persona(texto: str, nombre_archivo: str) -> dict:
    meta = {"nombre": nombre_archivo.capitalize(), "ciudad": "Buenos Aires, Argentina", "genero": "F"}
    m = _META_RE.search(texto)
    if m:
        for par in m.group(1).split("|"):
            if ":" in par:
                k, v = par.split(":", 1)
                k = k.strip().lower()
                if k in meta:
                    meta[k] = v.strip()
    return meta


def preparar_hogar_sim(meta: dict, perfil: str, continuar: bool = False) -> tuple[int, list]:
    """Deja el hogar de prueba listo: perfil, datos de la persona e historial.
    Al usar un hogar real, el simulador ejercita la MISMA resolución de config
    que producción (género, ciudad, medio) — por eso detecta bugs que un prompt
    armado a mano no puede ver.

    `continuar=True` CONSERVA el historial de la corrida anterior, para simular
    "otro día" con la misma persona. Es la única forma de reproducir la clase
    de bug donde un dato con fecha de una charla vieja se repite como actual.
    Devuelve (chat_id, historial_inicial).
    """
    sys.path.insert(0, str(BASE_DIR))
    from core import hogar as hogar_mod
    from core.utils import write_text_atomic, load_json

    d = hogar_mod.hogar_dir(HOGAR_SIM)
    d.mkdir(parents=True, exist_ok=True)
    write_text_atomic(hogar_mod.perfil_path(HOGAR_SIM), perfil)
    hogar_mod.escribir_state(HOGAR_SIM, {
        "owner_chat_id": HOGAR_SIM,
        "nombre_adulto_mayor": meta["nombre"],
        "ciudad": meta["ciudad"],
        "genero": meta["genero"],
        "perfil_completo": True,
    })
    (d / "alerta_pendiente.json").unlink(missing_ok=True)

    if continuar:
        historial = load_json(d / "historial.json", default=[]) or []
        print(f"[simulador] Continuando con {len(historial)} mensajes de la charla anterior")
        return HOGAR_SIM, historial

    (d / "historial.json").unlink(missing_ok=True)
    return HOGAR_SIM, []


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


def system_prompt_bot(perfil: str, core: str = "", nombre_adulto: str = "Marta", nombre_bot: str = "Aikiu") -> str:
    sys.path.insert(0, str(BASE_DIR))
    from core.utils import fecha_hora_es
    partes = [f"Tu nombre es {nombre_bot}. Hablás con {nombre_adulto}.\n"]
    if core:
        partes.append(f"## LINEAMIENTOS DEL SISTEMA\n{core}\n")
    partes.append(f"## PERFIL DE {nombre_adulto.upper()}\n{perfil}\n")
    partes.append(
        f"Fecha y hora actual: {fecha_hora_es()} (hora de Buenos Aires).\n"
        f"Respondé siempre en español rioplatense. Máximo 3 oraciones. "
        f"Nunca uses markdown."
    )
    # La detección de angustia (DISTRESS) ya NO se pide acá: en producción la
    # hace el agente vigía por separado. El simulador replica esa arquitectura
    # llamando a clasificar_distress aparte por cada turno (ver simular()).
    return "".join(partes)


def system_prompt_vigia(texto_usuario: str, nombre_adulto: str = "Marta") -> str:
    """Réplica del prompt del vigía de producción (aikiu.py::_prompt_vigia),
    para medir la detección de angustia con la arquitectura de dos agentes."""
    sys.path.insert(0, str(BASE_DIR))
    import aikiu
    return aikiu._prompt_vigia(texto_usuario, nombre_adulto)


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
            max_tokens=300,
            temperature=0.7,
            # Modelos con razonamiento (GLM-5): apagarlo — el "pensamiento"
            # consume el max_tokens (deja content vacío) y agrega latencia
            # que no queremos en una conversación de voz.
            extra_body={"reasoning": {"enabled": False}},
        )
        contenido = r.choices[0].message.content
        if not contenido:
            raise RuntimeError(f"{model} devolvió respuesta vacía (unavailable)")
        return contenido.strip()

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



def _enviar_a_usuario(chat, mensaje: str, reintentos: int = 2) -> str:
    """send_message a Gemini con tolerancia a respuestas vacías (safety
    filter / candidato vacío devuelve .text=None y rompía el lote)."""
    ultimo = None
    for _ in range(reintentos + 1):
        resp = chat.send_message(mensaje)
        texto = (resp.text or "").strip() if resp is not None else ""
        if texto:
            return texto
        ultimo = resp
        mensaje = "Continuá la conversación como tu personaje, con una frase corta."
    raise RuntimeError(f"Gemini devolvió respuesta vacía tras reintentos: {ultimo!r}")


async def simular(
    persona: str = "marta",
    turnos: int = 10,
    iteracion: int = 1,
    escenario: str | None = None,
    continuar: bool = False,
) -> tuple[list[dict], Path]:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")

    perfil = cargar_perfil_simulacion()
    persona_prompt = cargar_persona(persona)

    esc = cargar_escenario(escenario) if escenario else None
    if esc:
        persona_prompt += (
            f"\n\nESCENARIO DE ESTA CONVERSACIÓN (seguilo de forma natural, "
            f"sin nombrarlo explícitamente): {esc['consigna']}"
        )

    # Cargar lineamientos del sistema (aikiu_core.md)
    core_path = BASE_DIR / "aikiu_core.md"
    core = core_path.read_text(encoding="utf-8") if core_path.exists() else ""

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    # Agente A: Gemini simula al adulto mayor
    chat_usuario = gemini_client.chats.create(
        model="gemini-2.5-flash",
        config={"system_instruction": persona_prompt},
    )

    # Agente B: el bot REAL. En vez de rearmar un prompt paralelo, el
    # simulador llama a aikiu.generar_respuesta sobre un hogar de prueba, así
    # ejercita lo mismo que producción: resolución de config por hogar
    # (género, ciudad, medio), contexto del día, blacklist de temas, aviso de
    # historial multi-día, recordatorio por turno y el fallback de proveedor.
    sys.path.insert(0, str(BASE_DIR))
    import aikiu
    meta = _meta_persona(persona_prompt, persona)
    chat_sim, historial_bot = preparar_hogar_sim(meta, perfil, continuar=continuar)

    LOGS_SIM_DIR.mkdir(exist_ok=True)
    sufijo_esc = f"_{escenario}" if escenario else ""
    log_path = LOGS_SIM_DIR / f"iter{iteracion:02d}_{persona}{sufijo_esc}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"

    conversacion = []
    backend_actual = "?"

    sep = "─" * 60
    print(f"\n{sep}")
    etiqueta_esc = f" | Escenario: {esc['nombre']}" if esc else ""
    print(f"  Simulación — Iteración {iteracion} | Persona: {persona} | {turnos} turnos{etiqueta_esc}")
    print(f"{sep}\n")

    msg_usuario = _enviar_a_usuario(chat_usuario, "Iniciá la conversación como lo haría tu personaje.")

    for turno in range(turnos):
        print(f"[{persona.capitalize()}]: {msg_usuario}\n")

        # Camino real de producción: conversador primero, vigía después (igual
        # que handle_message, donde el vigía corre en background).
        raw = await aikiu.generar_respuesta(msg_usuario, historial_bot, chat_id=chat_sim)
        msg_bot_limpio, _ = aikiu.parse_llm_response(raw)
        # El vigía es una 2ª llamada a GLM-5 por turno. En el gate CONVERSACIONAL
        # (ciclo.py) su resultado no se evalúa —ninguna aserción mira el nivel de
        # distress— y el vigía ya se mide aparte y gratis en correr_vigia.py. Con
        # SIM_SKIP_VIGIA=1 se saltea y se ahorra ~15% del costo del gate, sin
        # perder señal: la respuesta del conversador es idéntica corra o no el
        # vigía (en producción corre en background, no la afecta).
        if os.getenv("SIM_SKIP_VIGIA") == "1":
            nivel, distress_motivo = 0, None
        else:
            nivel, distress_motivo = await aikiu.clasificar_distress(msg_usuario, chat_id=chat_sim)
        distress_raw = f"DISTRESS_LEVEL: {nivel}" if distress_motivo else None
        backend_actual = f"prod:{aikiu.CONFIG.get('modelo_llm', '?')}"

        historial_bot.append({"role": "user", "content": msg_usuario})
        historial_bot.append({"role": "assistant", "content": msg_bot_limpio})

        print(f"[Aikiu ({backend_actual})]:   {msg_bot_limpio}\n")
        print("─" * 40)

        conversacion.append({
            "turno": turno + 1,
            "ts": datetime.now(timezone.utc).isoformat(),
            "usuario": msg_usuario,
            "bot": msg_bot_limpio,
            "distress": distress_raw,
            "distress_motivo": distress_motivo,
            "backend": backend_actual,
        })

        if turno < turnos - 1:
            msg_usuario = _enviar_a_usuario(chat_usuario, msg_bot_limpio)

    # Persistimos el historial en el hogar de prueba para que una corrida con
    # --continuar (otro día) lo encuentre, igual que hace producción.
    from core.utils import write_json_atomic
    from core import hogar as hogar_mod
    write_json_atomic(hogar_mod.hogar_dir(chat_sim) / "historial.json", historial_bot[-40:])

    with open(log_path, "w", encoding="utf-8") as f:
        for entry in conversacion:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\n[simulador] Log guardado: {log_path.name} (backend final: {backend_actual})")
    return conversacion, log_path


if __name__ == "__main__":
    # Uso: python simulador/simulador.py [persona] [turnos] [escenario] [--continuar]
    #   ej.: python simulador/simulador.py marta 8 dolor_fisico
    #   multi-día: correr una vez normal y después con --continuar (conserva el
    #   historial, así se prueba que un dato de "ayer" no se repita como de hoy):
    #     python simulador/simulador.py marta 6 saludo
    #     python simulador/simulador.py marta 6 dia_siguiente --continuar
    args      = [a for a in sys.argv[1:] if not a.startswith("--")]
    continuar = "--continuar" in sys.argv
    persona   = args[0] if len(args) > 0 else "marta"
    turnos    = int(args[1]) if len(args) > 1 else 10
    escenario = args[2] if len(args) > 2 else None
    asyncio.run(simular(persona=persona, turnos=turnos, escenario=escenario, continuar=continuar))
