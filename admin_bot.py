"""
Bot de administración de Aikiu — uso exclusivo del operador.

Tercer bot de Telegram (separado de aikiu.py y familiar_bot.py) que provee
monitoreo y métricas vía comandos:

    /health     estado heartbeat + ping Telegram de cada instancia
    /llm        tokens consumidos, latencias, ratio de errores
    /metricas   actividad, alertas, aprendizajes, top temas
    /instancias lista de instancias detectadas
    /logs       últimas N líneas del log de una instancia
    /ayuda      este menú

TOFU sobre admin_state.json: el primer /start queda registrado como admin
único. Cualquier otro chat es rechazado silenciosamente.

Soporta multi-tenant a futuro vía AIKIU_REGISTRY: con la env var seteada,
descubre todas las instancias bajo ese directorio. Sin la env var, opera
sobre la instancia única que vive en BASE_DIR (la instalación actual).
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import Bot, BotCommand, Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from core import admin_state, heartbeat as hb_mod, usage as usage_mod
from core.instance import (
    BASE_DIR,
    descubrir_instancias,
    id_de,
    nombre_adulto_de,
)
from core.utils import load_json

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] admin %(message)s",
)
log = logging.getLogger("aikiu-admin")

ADMIN_TOKEN       = os.environ.get("ADMIN_BOT_TOKEN", "").strip()
BOT_TOKEN         = os.environ.get("BOT_TOKEN", "").strip()
FAMILIAR_TOKEN    = os.environ.get("FAMILIAR_BOT_TOKEN", "").strip()

# Umbral indicativo para alertar al admin si está por reventar el free tier.
# Groq free hoy ronda ~14.4k tokens/min y ~500k tokens/día por modelo; lo dejo
# configurable porque la cuota cambia y el admin puede tener tier pago.
LIMITE_TOKENS_DIA = int(os.environ.get("GROQ_DAILY_TOKEN_LIMIT", "500000"))


# ---------------------------------------------------------------------------
# Gate de autorización
# ---------------------------------------------------------------------------

def _es_admin_autorizado(chat_id: int) -> bool:
    return admin_state.es_admin(chat_id)


async def _rechazar_silencioso(update: Update, motivo: str) -> None:
    log.warning(f"acceso rechazado: chat_id={update.effective_chat.id} ({motivo})")


# ---------------------------------------------------------------------------
# Helpers de UI compartidos por todos los comandos
# ---------------------------------------------------------------------------

_SEMAFORO = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴", "ausente": "⚫"}
_ORDEN_ESTADO = {"ausente": 0, "rojo": 1, "amarillo": 2, "verde": 3}


def _hace(iso_ts: Optional[str], ahora: Optional[datetime] = None) -> str:
    """ISO timestamp → 'hace 30s' / 'hace 4 min' / 'hace 2h'. None → '—'."""
    if not iso_ts:
        return "—"
    try:
        ts = datetime.fromisoformat(iso_ts)
    except (ValueError, TypeError):
        return iso_ts
    delta = int(((ahora or datetime.now()) - ts).total_seconds())
    if delta < 0:
        return "ahora"
    if delta < 60:
        return f"hace {delta}s"
    if delta < 3600:
        return f"hace {delta // 60} min"
    if delta < 86400:
        h = delta // 3600
        m = (delta % 3600) // 60
        return f"hace {h}h {m}min" if m else f"hace {h}h"
    return f"hace {delta // 86400}d"


def _peor(estados: list[str]) -> str:
    """Devuelve el peor estado de una lista (ausente > rojo > amarillo > verde)."""
    if not estados:
        return "ausente"
    return min(estados, key=lambda e: _ORDEN_ESTADO.get(e, 0))


def _roles_esperados() -> list[str]:
    """Qué bots esperamos que estén corriendo según el .env.
    Si FAMILIAR_BOT_TOKEN no está, no contamos familiar como faltante."""
    esperados = ["aikiu"]
    if FAMILIAR_TOKEN and "PEGA_TU" not in FAMILIAR_TOKEN:
        esperados.append("familiar")
    return esperados


def _estado_instancia(hbs: dict, esperados: list[str]) -> str:
    """Peor estado entre los roles esperados de una instancia."""
    return _peor([hb_mod.estado(hbs.get(rol)) for rol in esperados])


def _sparkline(valores: list[int]) -> str:
    """[0,1,3,5,2] → '▁▂▄▇▃' usando 8 niveles unicode."""
    if not valores:
        return ""
    chars = "▁▂▃▄▅▆▇█"
    maximo = max(valores) or 1
    return "".join(
        chars[min(int(v / maximo * (len(chars) - 1)), len(chars) - 1)]
        for v in valores
    )


def _formato_bytes(n: int) -> str:
    """Tamaño de archivo legible."""
    for unidad in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unidad}" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# /start  +  /ayuda
# ---------------------------------------------------------------------------

MENU = (
    "*Aikiu Admin*\n"
    "_Monitoreo de tus instancias del bot._\n\n"
    "🩺 *Salud y diagnóstico*\n"
    "/health — estado de los bots (semáforo + ping a Telegram)\n"
    "/logs — últimas líneas del log (`/logs 50` para más, `/logs err` solo warnings)\n\n"
    "📊 *Uso y métricas*\n"
    "/llm — tokens del LLM hoy / 7 días / 30 días\n"
    "/metricas — operación: volumen, errores, latencias, archivos\n\n"
    "🗂 *Multi-instancia*\n"
    "/instancias — listar instancias detectadas\n\n"
    "/ayuda — este menú"
)

# Lista que Telegram muestra en el botón de menú azul al lado de la caja de texto.
# Las descripciones tienen que ser cortas (<=256 chars cada una, sin markdown).
COMANDOS_TELEGRAM = [
    BotCommand("health",     "Salud de los bots (semaforo + ping Telegram)"),
    BotCommand("llm",        "Uso del LLM: tokens y latencias"),
    BotCommand("metricas",   "Operacion: volumen, errores, latencias"),
    BotCommand("instancias", "Listar instancias detectadas"),
    BotCommand("logs",       "Ultimas lineas del log (/logs 50)"),
    BotCommand("ayuda",      "Menu de comandos"),
]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    nombre_tg = update.effective_user.first_name or "admin"

    if not admin_state.tiene_admin():
        if admin_state.registrar_admin(chat_id):
            log.warning(
                f"[ADMIN REGISTRADO] chat_id={chat_id} usuario_tg={nombre_tg!r} "
                f"hora={datetime.now().isoformat(timespec='seconds')}"
            )
            instancias = descubrir_instancias()
            await update.message.reply_text(
                f"✅ Hola *{nombre_tg}*, quedaste registrado como admin único.\n"
                f"_Detecté {len(instancias)} instancia(s) bajo monitoreo._\n\n{MENU}",
                parse_mode="Markdown",
            )
            return

    if not _es_admin_autorizado(chat_id):
        await _rechazar_silencioso(update, "no es admin")
        return

    await update.message.reply_text(
        f"Hola *{nombre_tg}* 👋\n\n{MENU}",
        parse_mode="Markdown",
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return
    await update.message.reply_text(MENU, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /instancias
# ---------------------------------------------------------------------------

def _resumen_instancia(d: Path) -> dict:
    """Datos básicos de una instancia para mostrar en /instancias y /health."""
    hbs = hb_mod.leer_heartbeats(d)
    nombre = nombre_adulto_de(d)
    return {
        "id": id_de(d),
        "dir": d,
        "nombre_adulto": nombre,
        "hbs": hbs,
        "hb_aikiu": hbs["aikiu"],
        "hb_familiar": hbs["familiar"],
    }


async def cmd_instancias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    instancias = [_resumen_instancia(d) for d in descubrir_instancias()]
    esperados = _roles_esperados()

    if not instancias:
        await update.message.reply_text(
            "No detecté ninguna instancia.\n"
            "_Si recién instalaste, arrancá `aikiu.py` y volvé a probar._",
            parse_mode="Markdown",
        )
        return

    cuenta_verdes = sum(
        1 for i in instancias if _estado_instancia(i["hbs"], esperados) == "verde"
    )

    lineas = [
        f"*🗂 Instancias detectadas: {len(instancias)}*",
        f"_{cuenta_verdes} de {len(instancias)} en verde._\n",
    ]

    for i in instancias:
        est = _estado_instancia(i["hbs"], esperados)
        icono = _SEMAFORO[est]
        hb_a = i["hb_aikiu"]
        hb_f = i["hb_familiar"]
        ultimo = _hace(hb_a.get("last_seen") if hb_a else None)
        owner = (hb_a or {}).get("owner_chat_id")
        owner_str = f"`{owner}`" if owner else "_(sin adulto registrado)_"

        lineas.append(f"{icono} *{i['nombre_adulto']}*  ·  id `{i['id']}`")
        lineas.append(f"   • Adulto: {owner_str}")
        lineas.append(f"   • Aikiu visto: {ultimo}")
        if "familiar" in esperados:
            ult_f = _hace(hb_f.get("last_seen") if hb_f else None)
            lineas.append(f"   • Familiar visto: {ult_f}")
        lineas.append("")

    lineas.append("_Para detalle de salud de cada bot: /health_")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

async def _ping_telegram(token: str) -> Optional[str]:
    """Devuelve el username del bot si responde, o None si falla."""
    if not token or "PEGA_TU" in token:
        return None
    try:
        async with Bot(token=token) as bot:
            me = await bot.get_me()
            return me.username or me.first_name
    except TelegramError as e:
        log.warning(f"ping Telegram falló: {e}")
        return None
    except Exception as e:
        log.warning(f"ping Telegram error inesperado: {e}")
        return None


def _icono_rol(hb: Optional[dict]) -> str:
    return _SEMAFORO[hb_mod.estado(hb)]


async def cmd_health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Ping en paralelo a los 3 bots conocidos
    ping_aikiu, ping_familiar, ping_admin = await asyncio.gather(
        _ping_telegram(BOT_TOKEN),
        _ping_telegram(FAMILIAR_TOKEN),
        _ping_telegram(ADMIN_TOKEN),
    )

    instancias = [_resumen_instancia(d) for d in descubrir_instancias()]
    esperados = _roles_esperados()

    # Headline: peor estado global → emoji + frase
    estados_globales = [_estado_instancia(i["hbs"], esperados) for i in instancias]
    pings_ok = sum(1 for p in (ping_aikiu, ping_admin) if p)  # familiar es opcional
    if "familiar" in esperados:
        pings_ok += 1 if ping_familiar else 0
    pings_total = len(esperados) + 1  # +1 por el admin mismo

    peor_global = _peor(estados_globales) if estados_globales else "ausente"
    icono_g = _SEMAFORO[peor_global]
    if peor_global == "verde" and pings_ok == pings_total:
        headline = f"{icono_g} *Todo OK* — {len(instancias)} instancia(s), {pings_ok}/{pings_total} bots respondiendo."
    elif peor_global == "verde":
        headline = f"🟡 *Bots vivos pero la API de Telegram falló para alguno* ({pings_ok}/{pings_total} ok)."
    elif peor_global == "amarillo":
        headline = f"{icono_g} *Algún bot tardando.* Mirá detalle abajo."
    else:
        headline = f"{icono_g} *Hay un bot caído o sin reportar.* Mirá detalle abajo."

    lineas = ["*🩺 Health check*", headline, ""]

    # Detalle por instancia (combinando heartbeat + ping Telegram)
    for i in instancias:
        nombre = i["nombre_adulto"]
        id_inst = i["id"]
        est_inst = _estado_instancia(i["hbs"], esperados)
        icono_inst = _SEMAFORO[est_inst]

        lineas.append(f"{icono_inst} *{nombre}* (`{id_inst}`)")

        # Aikiu
        hb_a = i["hb_aikiu"]
        uptime_a = hb_mod.formato_uptime(hb_mod.uptime_segundos(hb_a))
        visto_a = _hace(hb_a.get("last_seen") if hb_a else None)
        ping_a = f"@{ping_aikiu}" if ping_aikiu else "sin respuesta"
        lineas.append(
            f"   {_icono_rol(hb_a)} aikiu  ·  visto {visto_a}  ·  up {uptime_a}  ·  Telegram: {ping_a}"
        )

        # Familiar (si lo esperamos)
        if "familiar" in esperados:
            hb_f = i["hb_familiar"]
            uptime_f = hb_mod.formato_uptime(hb_mod.uptime_segundos(hb_f))
            visto_f = _hace(hb_f.get("last_seen") if hb_f else None)
            ping_f = f"@{ping_familiar}" if ping_familiar else "sin respuesta"
            lineas.append(
                f"   {_icono_rol(hb_f)} familiar  ·  visto {visto_f}  ·  up {uptime_f}  ·  Telegram: {ping_f}"
            )
        lineas.append("")

    # Admin (este proceso)
    ping_a_str = f"@{ping_admin}" if ping_admin else "sin respuesta"
    lineas.append(f"🛠 *Admin (este bot)* — Telegram: {ping_a_str}")

    # Tips si algo no anda
    if peor_global in ("rojo", "ausente"):
        lineas.append(
            "\n_Tip: si un bot dice 'sin respuesta', el proceso puede estar muerto. "
            "Mirá /logs y considerá reiniciar con `bash start.sh`._"
        )

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /llm
# ---------------------------------------------------------------------------

# Alias humanos para que no aparezca "llama-3.3-70b-versatile" crudo en el chat.
# Si un modelo nuevo no está acá, se usa el nombre tal cual (limpiado).
_ALIAS_MODELO = {
    "llama-3.3-70b-versatile": "LLM (conversación)",
    "whisper-large-v3":        "Whisper (transcripción)",
}


def _alias(modelo: str) -> str:
    return _ALIAS_MODELO.get(modelo, modelo)


def _semaforo_limite(tokens_hoy: int) -> tuple[str, str, str]:
    """Devuelve (emoji, descripción corta, porcentaje como string).
    El porcentaje se muestra como '<1%' cuando hay consumo positivo pero
    redondea a 0; así no parece que no se usó nada."""
    if LIMITE_TOKENS_DIA <= 0:
        return ("⚪", "sin límite configurado", "—")
    ratio = tokens_hoy / LIMITE_TOKENS_DIA
    pct_int = int(ratio * 100)
    if 0 < ratio < 0.01:
        pct_str = "<1%"
    else:
        pct_str = f"{pct_int}%"
    if pct_int >= 90:
        return ("🔴", "casi en el tope diario", pct_str)
    if pct_int >= 70:
        return ("🟡", "consumo alto", pct_str)
    if pct_int >= 30:
        return ("🟢", "consumo normal", pct_str)
    return ("🟢", "consumo bajo", pct_str)


def _formato_tokens(n: int) -> str:
    """1234 → '1.234', 1234567 → '1,2 M'. Útil para que los números grandes
    se lean de un vistazo sin tener que contar dígitos."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M".replace(".", ",")
    if n >= 10_000:
        return f"{n / 1_000:.0f}k"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".", ",")
    return str(n)


def _plural(n: int, singular: str, plural: str) -> str:
    """Helper para evitar el feo 'error(es)'. Devuelve solo la palabra, no el número."""
    return singular if n == 1 else plural


def _formato_latencia(ms: int) -> str:
    """812 → '812ms', 1110 → '1,1s'. Más legible para latencias de red."""
    if ms >= 1000:
        return f"{ms / 1000:.1f}s".replace(".", ",")
    return f"{ms}ms"


def _latencia_p50(lats: list[int]) -> str:
    """Latencia representativa. Con pocos samples no es estadística, lo anotamos."""
    if not lats:
        return "—"
    s = sorted(lats)
    k = (len(s) - 1) * 0.5
    f = int(k)
    c = min(f + 1, len(s) - 1)
    p50 = s[f] if f == c else int(s[f] + (s[c] - s[f]) * (k - f))
    base = _formato_latencia(p50)
    if len(lats) < 5:
        return f"{base} (n={len(lats)})"
    return base


def _fila_periodo(label: str, chat: dict) -> str:
    """Una fila de la tabla por período, formateada para alinearse en monoespaciado."""
    total = chat["total"]
    ok = chat["ok"]
    err = chat["error"]
    tok = _formato_tokens(chat["tokens_total"])
    if total == 0:
        ok_str = "—"
        err_str = "—"
    else:
        ok_str = str(ok)
        err_str = f"{err} ({round(err / total * 100)}%)" if err else "0"
    return f"{label:<8} {total:>4}    {ok_str:>5}    {tok:>6}    {err_str:>9}"


async def cmd_llm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    instancias = descubrir_instancias()
    lineas: list[str] = ["*Uso del LLM (Groq)*"]

    for d in instancias:
        nombre = nombre_adulto_de(d)
        id_inst = id_de(d)

        s_hoy = usage_mod.resumen_simple(d, dias=1)
        s_7d  = usage_mod.resumen_simple(d, dias=7)
        s_30d = usage_mod.resumen_simple(d, dias=30)

        chat_hoy = s_hoy["chat"]
        stt_hoy  = s_hoy["stt"]
        tokens_hoy = chat_hoy["tokens_total"]

        emoji, descr, pct = _semaforo_limite(tokens_hoy)

        lineas.append(f"\n*Instancia `{id_inst}` — {nombre}*")

        # Headline: estado del límite diario de un vistazo
        if LIMITE_TOKENS_DIA > 0:
            lineas.append(
                f"\n{emoji} {_formato_tokens(tokens_hoy)} de "
                f"{_formato_tokens(LIMITE_TOKENS_DIA)} tokens hoy "
                f"({pct} del límite — _{descr}_)"
            )
        else:
            lineas.append(f"\n{emoji} {_formato_tokens(tokens_hoy)} tokens hoy")

        # Si todo está en cero, evitar tablas y aviso amable.
        sin_actividad = (
            chat_hoy["total"] == 0 and stt_hoy["total"] == 0 and
            s_7d["chat"]["total"] == 0 and s_30d["chat"]["total"] == 0
        )
        if sin_actividad:
            lineas.append(
                "_Sin actividad todavía. Cuando el bot hable con el adulto"
                " o procese audios van a aparecer datos acá._"
            )
            continue

        # Tabla por período (chat). Bloque monoespaciado para que las
        # columnas se alineen en Telegram.
        lineas.append("\n*Conversación (LLM)*")
        lineas.append(
            "```\n"
            f"Período   Total      OK   Tokens   Errores\n"
            f"{_fila_periodo('Hoy',    s_hoy['chat'])}\n"
            f"{_fila_periodo('7 días', s_7d['chat'])}\n"
            f"{_fila_periodo('30 días', s_30d['chat'])}\n"
            "```"
        )

        # Detalle de hoy (tokens in/out + latencia con n explícito)
        if chat_hoy["ok"]:
            lineas.append(
                f"_Hoy:_ in {_formato_tokens(chat_hoy['tokens_in'])} · "
                f"out {_formato_tokens(chat_hoy['tokens_out'])} · "
                f"latencia {_latencia_p50(chat_hoy['latencias_ms'])}"
            )

        # STT siempre visible (aunque sea para decir que no hubo audios)
        lineas.append("\n*Transcripción (Whisper)*")
        if stt_hoy["total"] == 0 and s_7d["stt"]["total"] == 0:
            lineas.append("_sin audios procesados en la última semana_")
        else:
            lat = _latencia_p50(stt_hoy["latencias_ms"]) if stt_hoy["ok"] else "—"
            audio_mb = stt_hoy["bytes_audio"] / (1024 * 1024) if stt_hoy["bytes_audio"] else 0
            audio_str = f" · {audio_mb:.1f} MB".replace(".", ",") if audio_mb else ""
            err_stt = f" · ⚠ {stt_hoy['error']} {_plural(stt_hoy['error'], 'error', 'errores')}" if stt_hoy["error"] else ""
            lineas.append(
                f"_Hoy:_ {stt_hoy['ok']} {_plural(stt_hoy['ok'], 'transcripción', 'transcripciones')}"
                f" · latencia {lat}{audio_str}{err_stt}"
            )

        # Errores: desglose por tipo si hubo
        if chat_hoy["error"]:
            tipos = sorted(
                chat_hoy["errores_por_tipo"].items(),
                key=lambda kv: kv[1], reverse=True,
            )
            pct_err = round(chat_hoy["error"] / chat_hoy["total"] * 100)
            desglose = ", ".join(f"{n} {t}" for t, n in tipos)
            lineas.append(
                f"\n⚠️ *{chat_hoy['error']} de {chat_hoy['total']} llamadas fallaron hoy* "
                f"({pct_err}%): {desglose}.\nUsá /logs err para ver detalles."
            )

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /metricas
# ---------------------------------------------------------------------------

def _contar_familiares(d: Path) -> int:
    return len(load_json(d / "familiares.json", default=[]))


def _stats_dias(d: Path, n: int) -> list[tuple[str, dict]]:
    """Devuelve los últimos n días de stats.json en orden cronológico inverso."""
    stats = load_json(d / "stats.json", default={})
    dias = sorted(stats.keys(), reverse=True)[:n]
    return [(dia, stats[dia]) for dia in dias]


def _serie_mensajes_7d(d: Path) -> list[int]:
    """Mensajes por día para los últimos 7 días, de más viejo a más nuevo."""
    stats = load_json(d / "stats.json", default={})
    hoy = datetime.now().date()
    return [
        int(stats.get((hoy - timedelta(days=i)).strftime("%Y-%m-%d"), {}).get("mensajes", 0))
        for i in range(6, -1, -1)
    ]


def _tamano_logs(d: Path) -> tuple[int, int]:
    """Devuelve (tamaño_total_bytes, cantidad_archivos) del directorio logs/."""
    logs_dir = d / "logs"
    if not logs_dir.exists():
        return (0, 0)
    archivos = list(logs_dir.glob("*.md"))
    total = sum(a.stat().st_size for a in archivos if a.exists())
    return (total, len(archivos))


def _salud_archivos(d: Path) -> list[tuple[str, str, Path]]:
    """Estado de los archivos críticos. Devuelve (nombre, estado, path).
    Estado: 'ok', 'vacio', 'corrupto', 'falta'."""
    chequear = [
        ("state.json",     d / "state.json"),
        ("stats.json",     d / "stats.json"),
        ("usage.json",     d / "usage.json"),
        ("familiares.json", d / "familiares.json"),
        ("perfil.md",      d / "perfil.md"),
    ]
    resultado = []
    for nombre, path in chequear:
        if not path.exists():
            resultado.append((nombre, "falta", path))
            continue
        if path.stat().st_size == 0:
            resultado.append((nombre, "vacio", path))
            continue
        if path.suffix == ".json":
            try:
                import json as _json
                _json.loads(path.read_text(encoding="utf-8"))
                resultado.append((nombre, "ok", path))
            except Exception:
                resultado.append((nombre, "corrupto", path))
        else:
            resultado.append((nombre, "ok", path))
    return resultado


def _icono_salud(estado: str) -> str:
    return {"ok": "🟢", "vacio": "⚪", "corrupto": "🔴", "falta": "🟡"}.get(estado, "❓")


async def cmd_metricas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Métricas operativas: volumen, errores, latencias, archivos. Sin contenido
    de conversaciones (eso lo tiene el bot familiar con /aprendizajes y /stats)."""
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    instancias = [_resumen_instancia(d) for d in descubrir_instancias()]
    if not instancias:
        await update.message.reply_text(
            "No detecté ninguna instancia. Probá /instancias.",
            parse_mode="Markdown",
        )
        return

    lineas: list[str] = ["*🔧 Métricas operativas*\n"]

    for i in instancias:
        d = i["dir"]
        nombre = i["nombre_adulto"]
        id_inst = i["id"]

        if len(instancias) > 1:
            lineas.append(f"*— Instancia `{id_inst}` ({nombre}) —*\n")

        # ── 1. Procesos (uptime + reinicios visibles) ────────────────────
        hb_a = i["hb_aikiu"]
        hb_f = i["hb_familiar"]
        up_a = hb_mod.formato_uptime(hb_mod.uptime_segundos(hb_a))
        started_a = _hace(hb_a.get("started_at") if hb_a else None)
        lineas.append("⚙️ *Procesos*")
        lineas.append(f"   • Aikiu arrancado {started_a}  ·  uptime {up_a}")
        if "familiar" in _roles_esperados():
            up_f = hb_mod.formato_uptime(hb_mod.uptime_segundos(hb_f))
            started_f = _hace(hb_f.get("started_at") if hb_f else None)
            lineas.append(f"   • Familiar arrancado {started_f}  ·  uptime {up_f}")
        lineas.append("")

        # ── 2. Volumen de tráfico (count puro, sin contenido) ────────────
        serie7d = _serie_mensajes_7d(d)
        total_7d = sum(serie7d)
        msg_hoy = serie7d[-1]
        spark = _sparkline(serie7d)
        lineas.append("📈 *Tráfico de mensajes*")
        lineas.append(
            f"   • Hoy: {msg_hoy}  ·  últimos 7d: {total_7d}  "
            f"·  promedio {total_7d / 7:.1f}/día"
        )
        if spark:
            lineas.append(f"   • `{spark}`  _(hace 6d → hoy)_")
        lineas.append("")

        # ── 3. LLM: errores y latencias (lo que importa para troubleshoot) ─
        r_hoy = usage_mod.resumir(d, dias=1)
        r_7d  = usage_mod.resumir(d, dias=7)
        err_hoy = r_hoy["errores"]
        err_7d  = r_7d["errores"]
        llamadas_hoy = r_hoy["total_llamadas"] + err_hoy
        llamadas_7d  = r_7d["total_llamadas"]  + err_7d
        pct_err_hoy = (err_hoy / llamadas_hoy * 100) if llamadas_hoy else 0
        pct_err_7d  = (err_7d  / llamadas_7d  * 100) if llamadas_7d  else 0

        lat_p50_hoy = max(
            (m["latencia_p50_ms"] for m in r_hoy["por_modelo"].values()),
            default=0,
        )
        lat_p95_hoy = max(
            (m["latencia_p95_ms"] for m in r_hoy["por_modelo"].values()),
            default=0,
        )

        lineas.append("🤖 *LLM (Groq)*")
        if llamadas_hoy:
            lineas.append(
                f"   • Hoy: {llamadas_hoy} llamadas  ·  errores {err_hoy} ({pct_err_hoy:.1f}%)"
            )
            lineas.append(
                f"   • Latencia hoy: p50 {lat_p50_hoy}ms  ·  p95 {lat_p95_hoy}ms"
            )
        else:
            lineas.append("   • Hoy: sin llamadas todavía")
        if llamadas_7d:
            lineas.append(
                f"   • 7 días: {llamadas_7d} llamadas  ·  errores {err_7d} ({pct_err_7d:.1f}%)"
            )
        if err_hoy > 0 or pct_err_7d > 5:
            lineas.append("   ⚠️ _Tasa de errores elevada — mirá /logs err_")
        lineas.append("")

        # ── 4. Alertas distress (count operativo, sin contenido) ─────────
        alertas_7d = {1: 0, 2: 0, 3: 0}
        for _, s in _stats_dias(d, 7):
            dist = s.get("distress", {})
            for nivel in (1, 2, 3):
                alertas_7d[nivel] += int(dist.get(str(nivel), 0))
        total_alertas = sum(alertas_7d.values())
        if total_alertas:
            lineas.append("🚨 *Alertas distress disparadas (7d)*")
            lineas.append(
                f"   • Total: {total_alertas}  ·  "
                f"🟡 {alertas_7d[1]} · 🟠 {alertas_7d[2]} · 🔴 {alertas_7d[3]}"
            )
            lineas.append("")

        # ── 5. Suscripciones y configuración ─────────────────────────────
        n_familiares = _contar_familiares(d)
        owner_id = (hb_a or {}).get("owner_chat_id")
        lineas.append("👥 *Suscripciones*")
        lineas.append(
            f"   • Adulto registrado: {'`' + str(owner_id) + '`' if owner_id else '_(sin owner)_'}"
        )
        lineas.append(f"   • Familiares suscriptos: {n_familiares}")
        lineas.append("")

        # ── 6. Disco (tamaño de archivos persistentes) ───────────────────
        tam_logs, n_logs = _tamano_logs(d)
        tam_stats = (d / "stats.json").stat().st_size if (d / "stats.json").exists() else 0
        tam_usage = (d / "usage.json").stat().st_size if (d / "usage.json").exists() else 0
        tam_recep = (d / "receptividad.json").stat().st_size if (d / "receptividad.json").exists() else 0
        lineas.append("💾 *Disco*")
        lineas.append(f"   • logs/: {_formato_bytes(tam_logs)} en {n_logs} archivo(s)")
        lineas.append(
            f"   • stats: {_formato_bytes(tam_stats)}  ·  "
            f"usage: {_formato_bytes(tam_usage)}  ·  "
            f"receptividad: {_formato_bytes(tam_recep)}"
        )
        lineas.append("")

        # ── 7. Salud de archivos críticos ────────────────────────────────
        salud = _salud_archivos(d)
        problemas = [s for s in salud if s[1] != "ok"]
        if problemas:
            lineas.append("📂 *Archivos críticos*")
            for nombre_arch, estado, _ in salud:
                if estado != "ok":
                    lineas.append(f"   {_icono_salud(estado)} `{nombre_arch}` — {estado}")
            lineas.append("")
        else:
            lineas.append("📂 *Archivos críticos:* 🟢 todos OK\n")

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /logs
# ---------------------------------------------------------------------------

def _buscar_instancia(id_inst: str) -> Optional[Path]:
    for d in descubrir_instancias():
        if id_de(d) == id_inst:
            return d
    return None


def _tail_lineas(path: Path, n: int, solo_errores: bool = False) -> list[str]:
    """Devuelve las últimas n líneas del log, opcionalmente filtrando WARN/ERROR.

    Lee solo el final del archivo para no levantar megabytes a memoria.
    """
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            tamaño = f.tell()
            # Para filtro de errores leemos más bloque (los WARN/ERROR son escasos)
            bloque = min(tamaño, max(n * (2000 if solo_errores else 200), 4096))
            f.seek(max(0, tamaño - bloque))
            data = f.read().decode("utf-8", errors="replace")
        lineas = data.splitlines()
        if solo_errores:
            lineas = [
                l for l in lineas
                if "[WARNING]" in l or "[ERROR]" in l or "[CRITICAL]" in l
            ]
        return lineas[-n:]
    except Exception as e:
        return [f"(error leyendo log: {e})"]


async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    args = context.args or []
    instancias = descubrir_instancias()

    # Parsing flexible. Argumentos:
    #   /logs               → última instancia, 30 líneas, todo
    #   /logs 50            → 50 líneas
    #   /logs err           → solo WARNING/ERROR
    #   /logs <id> 50       → instancia explícita
    #   /logs <id> err 50   → combinado
    id_inst: Optional[str] = None
    n = 30
    solo_errores = False
    for a in args:
        a_low = a.lower()
        if a.isdigit():
            n = max(1, min(int(a), 200))
        elif a_low in ("err", "errors", "errores", "warn", "warnings"):
            solo_errores = True
        else:
            id_inst = a

    # Resolver instancia
    if id_inst:
        d = _buscar_instancia(id_inst)
        if d is None:
            ids_disponibles = ", ".join(f"`{id_de(x)}`" for x in instancias)
            await update.message.reply_text(
                f"❌ Instancia `{id_inst}` no encontrada.\n"
                f"Disponibles: {ids_disponibles}\n"
                f"_Probá: /instancias_",
                parse_mode="Markdown",
            )
            return
    elif len(instancias) == 1:
        d = instancias[0]
    else:
        ids = ", ".join(f"`{id_de(x)}`" for x in instancias)
        await update.message.reply_text(
            f"Hay {len(instancias)} instancias. Decime cuál:\n"
            f"`/logs <id> [N] [err]`\n\nIds: {ids}",
            parse_mode="Markdown",
        )
        return

    log_path = d / "aikiu.log"

    # Metadata del archivo
    if not log_path.exists():
        await update.message.reply_text(
            f"📄 *Log de `{id_de(d)}`*\n\n"
            f"No existe `aikiu.log` todavía. ¿El bot ya arrancó al menos una vez?",
            parse_mode="Markdown",
        )
        return

    size = log_path.stat().st_size
    mtime = datetime.fromtimestamp(log_path.stat().st_mtime).isoformat(
        timespec="seconds"
    )

    lineas = _tail_lineas(log_path, n, solo_errores=solo_errores)
    filtro = " (solo WARN/ERROR)" if solo_errores else ""

    if not lineas:
        cuerpo = "_(sin líneas que coincidan)_" if solo_errores else "_(log vacío)_"
        await update.message.reply_text(
            f"📄 *Log de `{id_de(d)}`*{filtro}\n"
            f"_Tamaño: {_formato_bytes(size)} · modificado {_hace(mtime)}_\n\n"
            f"{cuerpo}",
            parse_mode="Markdown",
        )
        return

    contenido = "\n".join(lineas)
    # Telegram limita a 4096 chars; truncar al final si hace falta
    overhead = 200  # para el header/footer
    if len(contenido) > 4096 - overhead:
        contenido = "…(truncado)…\n" + contenido[-(4096 - overhead - 20):]

    header = (
        f"📄 *Log de `{id_de(d)}`* — {len(lineas)} línea(s){filtro}\n"
        f"_Tamaño: {_formato_bytes(size)} · modificado {_hace(mtime)}_"
    )
    footer = (
        "\n_Tips: `/logs 100` (más líneas), `/logs err` (solo problemas)._"
        if not solo_errores
        else ""
    )

    await update.message.reply_text(
        f"{header}\n```\n{contenido}\n```{footer}",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not ADMIN_TOKEN or "PEGA_TU" in ADMIN_TOKEN:
        raise RuntimeError(
            "Falta ADMIN_BOT_TOKEN en .env. Creá un bot con @BotFather y pegá "
            "el token como ADMIN_BOT_TOKEN=..."
        )

    app = Application.builder().token(ADMIN_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ayuda", cmd_ayuda))
    app.add_handler(CommandHandler("help", cmd_ayuda))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("llm", cmd_llm))
    app.add_handler(CommandHandler("metricas", cmd_metricas))
    app.add_handler(CommandHandler("instancias", cmd_instancias))
    app.add_handler(CommandHandler("logs", cmd_logs))

    log.info("Bot admin iniciando...")
    if not admin_state.tiene_admin():
        log.warning(
            "Todavía no hay admin registrado. Apenas el bot esté arriba mandá /start "
            "desde tu Telegram para quedar bindeado como dueño único."
        )
    else:
        log.info(f"Admin registrado: chat_id={admin_state.admin_chat_id()}")

    async with app:
        await app.initialize()
        # Publica los comandos en Telegram para que aparezcan en el botón de menú
        # azul (al lado del campo de texto) apenas el admin abre el chat.
        try:
            await app.bot.set_my_commands(COMANDOS_TELEGRAM)
            log.info(f"Comandos publicados en Telegram: {len(COMANDOS_TELEGRAM)}")
        except Exception as e:
            log.warning(f"No pude publicar los comandos en Telegram: {e}")
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        hb_mod.iniciar_heartbeat("admin")
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
