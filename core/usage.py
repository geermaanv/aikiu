"""
Tracking de uso del LLM y de Whisper (Groq) por instancia.

Cada llamada a Groq se registra como una línea-objeto en usage.json
del directorio de la instancia. El admin lee este archivo y los
históricos rotados (usage.YYYY-MM.json) para armar reportes.

Formato de entrada:
    {
      "ts": "2026-05-22T15:03:21",
      "op": "chat" | "stt" | "error",
      "model": "llama-3.3-70b-versatile",
      "prompt_tokens": 1234,        # solo chat
      "completion_tokens": 456,     # solo chat
      "total_tokens": 1690,         # chat: prompt+completion; stt: 0
      "latencia_ms": 812,
      "bytes_audio": 12345,         # solo stt
      "error": "RateLimitError..."  # solo op=error
    }

Diseño:
- Append-only sobre una lista JSON. Se reescribe el archivo entero
  con escritura atómica (tmp + replace) para evitar corrupción.
- Lock asyncio por proceso para serializar escrituras concurrentes.
- Rotación: al iniciar cualquier registro, si la primera entrada del
  archivo es de un mes anterior al actual, se mueve a usage.YYYY-MM.json
  y se arranca uno nuevo. Mantiene usage.json siempre del mes en curso.
- Lectura para reportes: combina usage.json + cuantos usage.YYYY-MM.json
  hagan falta según el rango pedido.

Para que aikiu.py y familiar_bot.py no se ensucien con código repetido,
se exponen dos context managers async:

    async with timed_chat("modelo") as t:
        resp = await groq.chat.completions.create(...)
        t.set_usage(resp.usage)
    # registra automáticamente en __aexit__

    async with timed_stt("whisper-large-v3", bytes_audio) as t:
        result = await groq.audio.transcriptions.create(...)
    # registra automáticamente
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.instance import instance_dir

log = logging.getLogger("aikiu.usage")

USAGE_FILENAME = "usage.json"
_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Archivos
# ---------------------------------------------------------------------------

def _path_actual(dir_instancia: Optional[Path] = None) -> Path:
    return (dir_instancia or instance_dir()) / USAGE_FILENAME


def _path_archivo_mes(dir_instancia: Path, año: int, mes: int) -> Path:
    return dir_instancia / f"usage.{año:04d}-{mes:02d}.json"


def _leer(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _escribir_atomico(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".usage.", suffix=".json.tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _rotar_si_corresponde(path: Path, ahora: datetime) -> list[dict]:
    """
    Si usage.json arranca con entradas de un mes anterior, las mueve a
    usage.YYYY-MM.json y deja usage.json vacío para el mes en curso.

    Devuelve la lista a la que se van a appendear las nuevas entradas.
    """
    entradas = _leer(path)
    if not entradas:
        return []
    # Separar las del mes actual del resto
    actuales = []
    viejas_por_mes: dict[tuple[int, int], list[dict]] = {}
    for e in entradas:
        ts = e.get("ts", "")
        try:
            dt = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            actuales.append(e)
            continue
        if dt.year == ahora.year and dt.month == ahora.month:
            actuales.append(e)
        else:
            viejas_por_mes.setdefault((dt.year, dt.month), []).append(e)

    if not viejas_por_mes:
        return actuales

    # Mover lo viejo a sus archivos mensuales
    for (año, mes), lote in viejas_por_mes.items():
        archivo = _path_archivo_mes(path.parent, año, mes)
        previos = _leer(archivo)
        _escribir_atomico(archivo, previos + lote)
        log.info(f"usage: rotadas {len(lote)} entrada(s) a {archivo.name}")
    return actuales


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

async def _append(entrada: dict, dir_instancia: Optional[Path] = None) -> None:
    """Append serializado de una entrada."""
    path = _path_actual(dir_instancia)
    ahora = datetime.now()
    entrada.setdefault("ts", ahora.isoformat(timespec="seconds"))
    async with _lock:
        try:
            actuales = _rotar_si_corresponde(path, ahora)
            actuales.append(entrada)
            _escribir_atomico(path, actuales)
        except Exception as e:
            log.warning(f"usage: no pude registrar {entrada.get('op')}: {e}")


async def registrar_chat(
    model: str,
    usage_obj: Any,
    latencia_ms: int,
    dir_instancia: Optional[Path] = None,
) -> None:
    """Graba una llamada exitosa a chat.completions."""
    prompt_tokens = _attr(usage_obj, "prompt_tokens", 0)
    completion_tokens = _attr(usage_obj, "completion_tokens", 0)
    total_tokens = _attr(usage_obj, "total_tokens", prompt_tokens + completion_tokens)
    await _append({
        "op": "chat",
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "latencia_ms": int(latencia_ms),
    }, dir_instancia)


async def registrar_stt(
    model: str,
    latencia_ms: int,
    bytes_audio: int = 0,
    dir_instancia: Optional[Path] = None,
) -> None:
    """Graba una llamada exitosa a audio.transcriptions."""
    await _append({
        "op": "stt",
        "model": model,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "latencia_ms": int(latencia_ms),
        "bytes_audio": int(bytes_audio),
    }, dir_instancia)


async def registrar_error(
    op: str,
    model: str,
    latencia_ms: int,
    error: str,
    dir_instancia: Optional[Path] = None,
) -> None:
    """Graba un fallo (rate limit, timeout, etc.) para que /llm muestre el ratio de errores."""
    await _append({
        "op": "error",
        "subop": op,
        "model": model,
        "latencia_ms": int(latencia_ms),
        "error": (error or "")[:200],
    }, dir_instancia)


def _attr(obj: Any, name: str, default: int) -> int:
    """Lee un atributo de un objeto Groq usage (puede venir como dict o pydantic)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# Context managers para envolver llamadas
# ---------------------------------------------------------------------------

class _Timer:
    """Helper para que el bloque async with pueda dejar el usage al salir."""
    def __init__(self) -> None:
        self.usage: Any = None
        self.error: Optional[str] = None

    def set_usage(self, usage_obj: Any) -> None:
        self.usage = usage_obj


@asynccontextmanager
async def timed_chat(model: str, dir_instancia: Optional[Path] = None):
    """
    Mide latencia y registra una llamada a chat.completions.

    Uso:
        async with timed_chat(modelo) as t:
            resp = await groq.chat.completions.create(...)
            t.set_usage(resp.usage)
    """
    t = _Timer()
    inicio = datetime.now()
    try:
        yield t
    except Exception as e:
        latencia = int((datetime.now() - inicio).total_seconds() * 1000)
        await registrar_error("chat", model, latencia, repr(e), dir_instancia)
        raise
    else:
        latencia = int((datetime.now() - inicio).total_seconds() * 1000)
        await registrar_chat(model, t.usage, latencia, dir_instancia)


@asynccontextmanager
async def timed_stt(model: str, bytes_audio: int = 0, dir_instancia: Optional[Path] = None):
    """
    Mide latencia y registra una llamada a audio.transcriptions.

    Uso:
        async with timed_stt("whisper-large-v3", bytes_audio):
            result = await groq.audio.transcriptions.create(...)
    """
    inicio = datetime.now()
    try:
        yield
    except Exception as e:
        latencia = int((datetime.now() - inicio).total_seconds() * 1000)
        await registrar_error("stt", model, latencia, repr(e), dir_instancia)
        raise
    else:
        latencia = int((datetime.now() - inicio).total_seconds() * 1000)
        await registrar_stt(model, latencia, bytes_audio, dir_instancia)


# ---------------------------------------------------------------------------
# Lectura para reportes
# ---------------------------------------------------------------------------

def cargar_rango(
    dir_instancia: Path,
    desde: datetime,
    hasta: Optional[datetime] = None,
) -> list[dict]:
    """
    Carga todas las entradas de usage en [desde, hasta], combinando
    usage.json actual + los archivos mensuales que toquen el rango.
    """
    hasta = hasta or datetime.now()
    entradas: list[dict] = []

    # Archivos mensuales que tocan el rango
    cursor = datetime(desde.year, desde.month, 1)
    fin_mes = datetime(hasta.year, hasta.month, 1)
    while cursor <= fin_mes:
        archivo = _path_archivo_mes(dir_instancia, cursor.year, cursor.month)
        if archivo.exists():
            entradas.extend(_leer(archivo))
        # avanzar un mes
        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1)
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1)

    # Archivo actual (puede contener entradas del mes en curso o anteriores aún no rotadas)
    entradas.extend(_leer(_path_actual(dir_instancia)))

    # Filtrar por rango y deduplicar (improbable pero por las dudas)
    filtradas = []
    for e in entradas:
        try:
            ts = datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError, TypeError):
            continue
        if desde <= ts <= hasta:
            filtradas.append(e)
    return filtradas


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    s = sorted(valores)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _clasificar_error(msg: str) -> str:
    """Mapea el string del error a una etiqueta corta y legible para el admin.
    El orden de los checks importa: lo más específico primero."""
    m = (msg or "").lower()
    if "ratelimiterror" in m or "rate limit" in m or "429" in m:
        return "rate limit (429)"
    if "timeout" in m:
        return "timeout"
    if "401" in m or "unauthorized" in m or "invalid api key" in m:
        return "auth (401)"
    if "503" in m or "service unavailable" in m:
        return "server (503)"
    if "500" in m or "internal" in m:
        return "server (500)"
    if "connection" in m:
        return "conexión"
    return "otro"


def resumen_simple(dir_instancia: Path, dias: int = 1) -> dict:
    """
    Resumen separado por tipo de operación (chat / stt) y con errores
    clasificados, pensado para que /llm lo presente sin hacer cuentas.

    Estructura:
        {
          "rango_dias": 1,
          "chat": {
            "ok": int, "error": int, "total": int,
            "tokens_total": int, "tokens_in": int, "tokens_out": int,
            "latencias_ms": [int, ...],   # solo de llamadas ok
            "errores_por_tipo": {"rate limit (429)": 8, ...},
          },
          "stt": {
            "ok": int, "error": int, "total": int,
            "latencias_ms": [int, ...],
            "bytes_audio": int,
            "errores_por_tipo": {...},
          }
        }
    """
    desde = datetime.now() - timedelta(days=dias)
    entradas = cargar_rango(dir_instancia, desde)

    chat = {
        "ok": 0, "error": 0,
        "tokens_total": 0, "tokens_in": 0, "tokens_out": 0,
        "latencias_ms": [], "errores_por_tipo": {},
    }
    stt = {
        "ok": 0, "error": 0,
        "latencias_ms": [], "bytes_audio": 0,
        "errores_por_tipo": {},
    }

    for e in entradas:
        op = e.get("op")
        if op == "chat":
            chat["ok"] += 1
            chat["tokens_in"] += int(e.get("prompt_tokens", 0))
            chat["tokens_out"] += int(e.get("completion_tokens", 0))
            chat["tokens_total"] += int(e.get("total_tokens", 0))
            chat["latencias_ms"].append(int(e.get("latencia_ms", 0)))
        elif op == "stt":
            stt["ok"] += 1
            stt["latencias_ms"].append(int(e.get("latencia_ms", 0)))
            stt["bytes_audio"] += int(e.get("bytes_audio", 0))
        elif op == "error":
            subop = e.get("subop") or "chat"
            tipo = _clasificar_error(e.get("error", ""))
            destino = chat if subop == "chat" else stt
            destino["error"] += 1
            destino["errores_por_tipo"][tipo] = destino["errores_por_tipo"].get(tipo, 0) + 1

    chat["total"] = chat["ok"] + chat["error"]
    stt["total"] = stt["ok"] + stt["error"]
    return {"rango_dias": dias, "chat": chat, "stt": stt}


def resumir(dir_instancia: Path, dias: int = 7) -> dict:
    """
    Devuelve un resumen para reportar al admin:
        {
          "rango_dias": 7,
          "total_llamadas": N,
          "errores": M,
          "por_modelo": {
              "llama-3.3-70b-versatile": {
                  "llamadas": ..., "prompt_tokens": ..., "completion_tokens": ...,
                  "total_tokens": ..., "latencia_p50": ..., "latencia_p95": ...
              },
              ...
          },
          "por_dia": {"2026-05-22": {"llamadas": N, "total_tokens": T}, ...}
        }
    """
    desde = datetime.now() - timedelta(days=dias)
    entradas = cargar_rango(dir_instancia, desde)
    por_modelo: dict[str, dict] = {}
    por_dia: dict[str, dict] = {}
    errores = 0

    for e in entradas:
        if e.get("op") == "error":
            errores += 1
            continue
        modelo = e.get("model", "?")
        d = por_modelo.setdefault(modelo, {
            "llamadas": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "_latencias": [],
        })
        d["llamadas"] += 1
        d["prompt_tokens"] += int(e.get("prompt_tokens", 0))
        d["completion_tokens"] += int(e.get("completion_tokens", 0))
        d["total_tokens"] += int(e.get("total_tokens", 0))
        d["_latencias"].append(int(e.get("latencia_ms", 0)))

        try:
            dia = datetime.fromisoformat(e["ts"]).strftime("%Y-%m-%d")
        except (KeyError, ValueError, TypeError):
            continue
        pd = por_dia.setdefault(dia, {"llamadas": 0, "total_tokens": 0})
        pd["llamadas"] += 1
        pd["total_tokens"] += int(e.get("total_tokens", 0))

    # Calcular percentiles y limpiar las listas internas
    for modelo, d in por_modelo.items():
        lats = d.pop("_latencias")
        d["latencia_p50_ms"] = int(_percentil(lats, 0.50))
        d["latencia_p95_ms"] = int(_percentil(lats, 0.95))

    return {
        "rango_dias": dias,
        "total_llamadas": sum(d["llamadas"] for d in por_modelo.values()),
        "errores": errores,
        "por_modelo": por_modelo,
        "por_dia": dict(sorted(por_dia.items(), reverse=True)),
    }
