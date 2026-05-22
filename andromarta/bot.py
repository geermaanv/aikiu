"""
Andromarta — humanoide sintético que conversa con Aikiu como si fuera Marta.

Corre como cliente de usuario de Telegram (NO es un bot): se loguea con un
número de teléfono propio vía MTProto/Telethon y chatea con el bot principal
(@aikiu_bot o el username que pongas en ANDROMARTA_AIKIU_USERNAME).

Para observar la conversación: abrí Telegram con la misma cuenta en tu
celular o en Telegram Desktop. Vas a ver todo en tiempo real, idéntico a
una charla humana cualquiera.

Variables de entorno (andromarta/.env — propio, separado del .env raíz):
    ANDROMARTA_API_ID            api_id de my.telegram.org (cliente de USUARIO)
    ANDROMARTA_API_HASH          api_hash de my.telegram.org
    ANDROMARTA_PHONE             +5491138...
    ANDROMARTA_SESSION           ruta del .session (default: andromarta/data/andromarta.session)
    ANDROMARTA_AIKIU_USERNAME    @aikiu_bot o similar (sin @ también vale)
    ANDROMARTA_VOZ_PROB          probabilidad 0.0-1.0 de responder en voz (default 0.4)
    GROQ_API_KEY                 misma key que usa Aikiu (duplicada acá por independencia)

IMPORTANTE: el archivo .session contiene credenciales sensibles. Está en
.gitignore. Si alguien obtiene ese archivo, ES esa cuenta de Telegram.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ANDROMARTA_DIR = Path(__file__).resolve().parent
REPO_ROOT = ANDROMARTA_DIR.parent
# Cuando se ejecuta como `python andromarta/bot.py`, Python agrega
# `andromarta/` al sys.path pero no la raíz del repo. Insertamos la raíz
# para que `core.*` y el paquete `andromarta` se resuelvan correctamente.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from groq import AsyncGroq
from telethon import TelegramClient, events

from core import heartbeat as hb_mod
from core import usage as usage_mod
from core.tts import sintetizar
from andromarta import memoria as memoria_mod
from andromarta import scheduler as scheduler_mod
from andromarta.generador import responder

load_dotenv(ANDROMARTA_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] andromarta %(message)s",
)
log = logging.getLogger("andromarta")
logging.getLogger("telethon").setLevel(logging.WARNING)  # menos ruido de la lib

# ---------------------------------------------------------------------------
# Config desde env
# ---------------------------------------------------------------------------

API_ID_RAW       = os.environ.get("ANDROMARTA_API_ID", "").strip()
API_HASH         = os.environ.get("ANDROMARTA_API_HASH", "").strip()
PHONE            = os.environ.get("ANDROMARTA_PHONE", "").strip()
SESSION          = os.environ.get(
    "ANDROMARTA_SESSION",
    str(ANDROMARTA_DIR / "data" / "andromarta.session"),
).strip()
AIKIU_USERNAME   = os.environ.get("ANDROMARTA_AIKIU_USERNAME", "").strip().lstrip("@")
NOMBRE_CLARA     = os.environ.get("ANDROMARTA_NOMBRE_CLARA", "Clara").strip()
MODELO           = os.environ.get("ANDROMARTA_MODELO", "llama-3.3-70b-versatile").strip()
VOZ_TTS          = os.environ.get("ANDROMARTA_VOZ_TTS", "es-AR-ElenaNeural").strip()
VOZ_PROB         = float(os.environ.get("ANDROMARTA_VOZ_PROB", "0.4"))
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY", "").strip()


def _validar_config() -> None:
    """Valida que las variables obligatorias estén presentes y sean usables."""
    faltantes = []
    if not API_ID_RAW or not API_ID_RAW.isdigit():
        faltantes.append("ANDROMARTA_API_ID (entero, de my.telegram.org)")
    if not API_HASH or "PEGA_TU" in API_HASH:
        faltantes.append("ANDROMARTA_API_HASH")
    if not PHONE or "PEGA_TU" in PHONE:
        faltantes.append("ANDROMARTA_PHONE (con prefijo internacional, ej. +5491138...)")
    if not AIKIU_USERNAME or "PEGA_TU" in AIKIU_USERNAME:
        faltantes.append("ANDROMARTA_AIKIU_USERNAME (username del bot Aikiu, ej. aikiu_test_bot)")
    if not GROQ_API_KEY or "PEGA_TU" in GROQ_API_KEY:
        faltantes.append("GROQ_API_KEY")
    if faltantes:
        raise RuntimeError(
            "Falta(n) variable(s) en .env:\n  - " + "\n  - ".join(faltantes)
        )


# ---------------------------------------------------------------------------
# Estado global del proceso
# ---------------------------------------------------------------------------

groq = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
client: TelegramClient | None = None
aikiu_entity = None  # se resuelve en run() después del start()
_background_tasks: set[asyncio.Task] = set()


def _bg(coro) -> asyncio.Task:
    """Crea task en background con strong ref (mismo patrón que aikiu.py)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# ---------------------------------------------------------------------------
# STT — transcribir audios que llegan de Aikiu
# ---------------------------------------------------------------------------

async def _transcribir(ogg_path: Path) -> str:
    bytes_audio = ogg_path.stat().st_size if ogg_path.exists() else 0
    async with usage_mod.timed_stt("whisper-large-v3", bytes_audio):
        with open(ogg_path, "rb") as f:
            result = await groq.audio.transcriptions.create(
                file=(ogg_path.name, f, "audio/ogg"),
                model="whisper-large-v3",
                language="es",
                response_format="text",
            )
    texto = result.strip() if isinstance(result, str) else result.text.strip()
    log.info(f"STT (Clara dijo): '{texto}'")
    return texto


# ---------------------------------------------------------------------------
# Ritmo humano — pausas y "escribiendo..."
# ---------------------------------------------------------------------------

async def _pausa_lectura(texto: str) -> None:
    """Tiempo que tarda Marta en 'leer' lo que llegó."""
    base = 1.5
    extra = min(8, len(texto) / 25)
    await asyncio.sleep(random.uniform(base, base + extra))


async def _pausa_tipeo(texto: str) -> float:
    """Tiempo que tarda Marta en 'tipear' la respuesta. Devuelve los seg dormidos."""
    base = 2.0
    # Adulto mayor tipea lento: ~3 chars/seg + ruido
    estimado = len(texto) / 3.0
    duracion = max(base, min(20, estimado + random.uniform(-1, 2)))
    await asyncio.sleep(duracion)
    return duracion


# ---------------------------------------------------------------------------
# Envío a Aikiu (texto o voz)
# ---------------------------------------------------------------------------

async def _enviar_texto(texto: str) -> None:
    async with client.action(aikiu_entity, "typing"):
        await _pausa_tipeo(texto)
        await client.send_message(aikiu_entity, texto)
    log.info(f"Andromarta → Aikiu (texto): '{texto}'")


async def _enviar_voz(texto: str) -> None:
    async with client.action(aikiu_entity, "voice"):
        # El "tipeo" para voz es más corto: la voz se graba más rápido que se escribe
        await asyncio.sleep(random.uniform(2.0, 5.0))
        with tempfile.TemporaryDirectory() as tmp:
            ogg = Path(tmp) / "andromarta.ogg"
            await sintetizar(texto, ogg, voz=VOZ_TTS)
            await client.send_file(aikiu_entity, str(ogg), voice_note=True)
    log.info(f"Andromarta → Aikiu (voz): '{texto}'")


async def _enviar_respuesta(texto: str, prefiere_voz: bool) -> None:
    """Decide formato y envía. Si la voz falla, cae a texto."""
    if not texto:
        log.warning("Respuesta vacía del LLM, no se envía nada")
        return
    if prefiere_voz and random.random() < VOZ_PROB:
        try:
            await _enviar_voz(texto)
            return
        except Exception as e:
            log.warning(f"TTS/envío de voz falló, mando como texto: {e}")
    await _enviar_texto(texto)


# ---------------------------------------------------------------------------
# Handlers de Telethon — cuando Clara escribe / habla
# ---------------------------------------------------------------------------

async def _on_clara_msg(event: events.NewMessage.Event) -> None:
    """Llega un mensaje de Aikiu — Andromarta lo procesa y responde."""
    msg = event.message
    if not msg:
        return

    es_voz = bool(msg.voice)
    texto_clara: str | None = None

    try:
        if es_voz:
            with tempfile.TemporaryDirectory() as tmp:
                ogg = Path(tmp) / "clara.ogg"
                await msg.download_media(file=str(ogg))
                texto_clara = await _transcribir(ogg)
        else:
            texto_clara = (msg.text or "").strip()
    except Exception as e:
        log.warning(f"Error procesando mensaje entrante: {e}")
        return

    if not texto_clara:
        log.info("Mensaje entrante sin texto utilizable, ignoro")
        return

    log.info(f"Clara → Andromarta ({'voz' if es_voz else 'texto'}): '{texto_clara}'")

    historial = memoria_mod.cargar_historial()
    memoria_mod.agregar_turno(historial, "user", texto_clara)

    await _pausa_lectura(texto_clara)

    try:
        respuesta = await responder(
            groq=groq,
            modelo=MODELO,
            historial=historial,
            nombre_clara=NOMBRE_CLARA,
            mensaje_de_clara=texto_clara,
        )
    except Exception as e:
        log.error(f"Generación de respuesta falló: {e}")
        return

    memoria_mod.agregar_turno(historial, "assistant", respuesta)
    # Si Clara mandó voz, hay más chance de que Marta también responda en voz
    prefiere_voz = es_voz or random.random() < VOZ_PROB
    await _enviar_respuesta(respuesta, prefiere_voz=prefiere_voz)


# ---------------------------------------------------------------------------
# Iniciativa — Andromarta arranca conversación sola
# ---------------------------------------------------------------------------

async def _disparar_iniciativa() -> None:
    """Callback del scheduler: genera un mensaje de apertura y lo manda."""
    if aikiu_entity is None:
        log.warning("Iniciativa: aikiu_entity no resuelto todavía, salteo")
        return

    historial = memoria_mod.cargar_historial()
    try:
        mensaje = await responder(
            groq=groq,
            modelo=MODELO,
            historial=historial,
            nombre_clara=NOMBRE_CLARA,
            mensaje_de_clara=None,  # señal de "iniciativa"
        )
    except Exception as e:
        log.error(f"Iniciativa: generación falló: {e}")
        return

    memoria_mod.agregar_turno(historial, "assistant", mensaje)
    prefiere_voz = random.random() < VOZ_PROB
    await _enviar_respuesta(mensaje, prefiere_voz=prefiere_voz)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run() -> None:
    global client, aikiu_entity

    _validar_config()

    log.info("=" * 50)
    log.info(f"Andromarta arrancando — chateará con @{AIKIU_USERNAME}")
    log.info("=" * 50)

    client = TelegramClient(SESSION, int(API_ID_RAW), API_HASH)
    await client.start(phone=PHONE)
    log.info("Sesión de Telegram lista.")

    try:
        aikiu_entity = await client.get_entity(AIKIU_USERNAME)
    except Exception as e:
        log.error(
            f"No pude encontrar al bot Aikiu (@{AIKIU_USERNAME}). "
            f"¿Iniciaste un chat con él al menos una vez desde esta cuenta? "
            f"Detalle: {e}"
        )
        await client.disconnect()
        return

    log.info(f"Bot Aikiu resuelto: id={aikiu_entity.id}")

    # Heartbeat (mismo patrón que aikiu/familiar/admin)
    hb_mod.iniciar_heartbeat("andromarta")

    # Handler para mensajes del bot Aikiu
    client.add_event_handler(
        _on_clara_msg,
        events.NewMessage(from_users=aikiu_entity, incoming=True),
    )

    # Loop de iniciativa
    _bg(scheduler_mod.loop_iniciativa(_disparar_iniciativa))

    log.info(
        f"Escuchando mensajes de @{AIKIU_USERNAME}. "
        f"Voz prob={VOZ_PROB}, modelo={MODELO}. Ctrl+C para detener."
    )

    # Marca el último mensaje "de Clara" como ahora para que el scheduler no
    # dispare iniciativa inmediatamente al arrancar
    historial = memoria_mod.cargar_historial()
    if not historial:
        log.info("Historial vacío: mandando /start para registrar primer contacto")
        memoria_mod.agregar_turno(historial, "user", "[inicio de sesión Andromarta]")
        try:
            await client.send_message(aikiu_entity, "/start")
        except Exception as e:
            log.warning(f"No pude enviar /start a Aikiu: {e}")

    try:
        await client.run_until_disconnected()
    finally:
        for t in list(_background_tasks):
            t.cancel()
        log.info("Andromarta apagándose.")


def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info(f"Detenido por teclado a las {_ts()}.")
