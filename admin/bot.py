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

TOFU sobre admin/admin_state.json: el primer /start queda registrado como
admin único. Cualquier otro chat es rechazado silenciosamente.

Soporta multi-tenant a futuro vía AIKIU_REGISTRY: con la env var seteada,
descubre todas las instancias bajo ese directorio. Sin la env var, opera
sobre la instancia única que vive en BASE_DIR (la instalación actual).

Todo lo propio del bot admin vive en admin/: este módulo (admin/bot.py),
el código de estado (admin/state.py), el JSON TOFU (admin/admin_state.json)
y su heartbeat (admin/heartbeat-admin.json). El resto del repo no depende
de admin/.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

ADMIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = ADMIN_DIR.parent
# Cuando se ejecuta como `python admin/bot.py`, Python agrega `admin/` al
# sys.path pero no la raíz del repo. Insertamos la raíz para que `core.*` y
# el paquete `admin` se resuelvan correctamente. Lo mismo hace andromarta/bot.py.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv
from telegram import Bot, BotCommand, Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

from core import heartbeat as hb_mod, llm_limits, usage as usage_mod
from core import hogar as hogar_mod
from core import invites as invites_mod
from core import familiar_state as fam_state_mod
from core.instance import (
    BASE_DIR,
    descubrir_instancias,
    id_de,
    nombre_adulto_de,
)
from core.utils import load_json
from admin import state as admin_state

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] admin %(message)s",
)
log = logging.getLogger("aikiu-admin")

ADMIN_TOKEN       = os.environ.get("ADMIN_BOT_TOKEN", "").strip()
BOT_TOKEN         = os.environ.get("BOT_TOKEN", "").strip()
FAMILIAR_TOKEN    = os.environ.get("FAMILIAR_BOT_TOKEN", "").strip()

# Override manual del TPD para el aviso de cuota en /llm.
# Si no está seteado (o no es un entero positivo) el admin usa los límites
# del catálogo core/llm_limits.py por cada modelo realmente en uso. El
# override existe para usuarios con tier pago de Groq, que tienen cuotas
# distintas a las del catálogo gratuito. Ver:
#     https://console.groq.com/docs/rate-limits
_raw_limite = os.environ.get("GROQ_DAILY_TOKEN_LIMIT", "").strip()
LIMITE_TOKENS_DIA_OVERRIDE: Optional[int] = (
    int(_raw_limite) if _raw_limite.isdigit() and int(_raw_limite) > 0 else None
)


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


def _escape_md(text: object) -> str:
    """Escapa los caracteres especiales del Markdown v1 de Telegram.

    Necesario para cualquier texto controlado por el usuario (nombres de
    adultos/familiares, etc.) que se inyecta en mensajes con
    `parse_mode="Markdown"`. Sin esto, un nombre con `_`, `*`, `` ` `` o `[`
    rompe el parser y Telegram devuelve 400 BadRequest.
    """
    s = str(text) if text is not None else ""
    for ch in ("_", "*", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s


async def _reply_md_safe(message, text: str) -> None:
    """Envía un mensaje con `parse_mode="Markdown"`. Si Telegram rechaza el
    Markdown (entidades mal cerradas, anidadas, etc.) reintenta como texto
    plano para que el admin reciba el contenido aunque pierda el formato.

    El bug que motivó este helper: Markdown legacy NO soporta anidar
    entidades (ej. `` ` `` dentro de `_..._`) y devuelve 400 BadRequest, lo
    que dejaba al admin sin respuesta y solo con un traceback en los logs.
    """
    try:
        await message.reply_text(text, parse_mode="Markdown")
    except BadRequest as e:
        log.warning(f"Markdown parse falló ({e}); reintentando como texto plano")
        await message.reply_text(text)


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
    "/instancias — listar instancias detectadas\n"
    "/hogares — listar hogares multi-tenant (un hogar por adulto)\n"
    "/borrar — borrar un hogar con confirmación (`/borrar <chat_id>`)\n\n"
    "👥 *Equipo*\n"
    "/admins — ver los chat_ids con permiso de admin\n"
    "/quitar\\_admin — quitar a un admin (`/quitar_admin <chat_id>`)\n\n"
    "/ayuda — este menú"
)

# Lista que Telegram muestra en el botón de menú azul al lado de la caja de texto.
# Las descripciones tienen que ser cortas (<=256 chars cada una, sin markdown).
COMANDOS_TELEGRAM = [
    BotCommand("health",       "Salud de los bots (semaforo + ping Telegram)"),
    BotCommand("llm",          "Uso del LLM: tokens y latencias"),
    BotCommand("metricas",     "Operacion: volumen, errores, latencias"),
    BotCommand("instancias",   "Listar instancias detectadas"),
    BotCommand("hogares",      "Listar hogares multi-tenant"),
    BotCommand("borrar",       "Borrar hogar: /borrar <chat_id>"),
    BotCommand("logs",         "Ultimas lineas del log (/logs 50)"),
    BotCommand("admins",       "Ver chat_ids con permiso de admin"),
    BotCommand("quitar_admin", "Quitar un admin: /quitar_admin <chat_id>"),
    BotCommand("ayuda",        "Menu de comandos"),
]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gestiona el alta de admins en modo cupo abierto.

    Cada /start desde un chat distinto suma un admin nuevo hasta llenar el
    cupo (ADMIN_MAX_USERS, default 5). Los siguientes /start de chats no
    registrados se rechazan en silencio. Admins ya registrados ven el menú.
    """
    chat_id = update.effective_chat.id
    nombre_tg = update.effective_user.first_name or "admin"

    if _es_admin_autorizado(chat_id):
        await update.message.reply_text(
            f"Hola *{nombre_tg}* 👋\n\n{MENU}",
            parse_mode="Markdown",
        )
        return

    if not admin_state.hay_cupo():
        await _rechazar_silencioso(
            update,
            f"cupo lleno ({admin_state.admin_count()}/{admin_state.admins_max()})",
        )
        return

    if not admin_state.registrar_admin(chat_id):
        # No quedó cupo entre el chequeo y el alta (carrera muy improbable),
        # o env override impide registros: el silencio sigue siendo lo correcto.
        await _rechazar_silencioso(update, "no se pudo registrar")
        return

    log.warning(
        f"[ADMIN REGISTRADO] chat_id={chat_id} usuario_tg={nombre_tg!r} "
        f"posicion={admin_state.admin_count()}/{admin_state.admins_max()} "
        f"hora={datetime.now().isoformat(timespec='seconds')}"
    )
    instancias = descubrir_instancias()
    cupo_msg = (
        "primer admin registrado"
        if admin_state.admin_count() == 1
        else f"admin {admin_state.admin_count()} de {admin_state.admins_max()} registrados"
    )
    await update.message.reply_text(
        f"✅ Hola *{nombre_tg}*, {cupo_msg}.\n"
        f"_Detecté {len(instancias)} instancia(s) bajo monitoreo._\n\n{MENU}",
        parse_mode="Markdown",
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return
    await update.message.reply_text(MENU, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# /admins  +  /quitar_admin
# ---------------------------------------------------------------------------

async def cmd_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    admins = admin_state.listar_admins()
    cupo = admin_state.admins_max()
    actual = len(admins)
    env_lock = admins and admins[0].get("source") == "env"

    lineas = [f"*👥 Admins registrados:* {actual}/{cupo}"]
    if env_lock:
        lineas.append(
            "_La lista está fijada por la env var ADMIN_CHAT_IDS — no se "
            "puede modificar desde el bot. Editá el `.env` y reiniciá._"
        )
    elif admin_state.hay_cupo():
        lineas.append(
            f"_Queda(n) {cupo - actual} lugar(es). Cualquiera que mande /start "
            f"al bot va a quedar registrado automáticamente hasta llenar el cupo._"
        )
    else:
        lineas.append("_Cupo lleno: nuevos /start se rechazan en silencio._")

    lineas.append("")
    quien_soy = update.effective_chat.id
    for i, a in enumerate(admins, 1):
        cid = a["chat_id"]
        marca = " ← _vos_" if int(cid) == int(quien_soy) else ""
        if a.get("source") == "env":
            lineas.append(f"{i}. `{cid}` _(desde .env)_{marca}")
        else:
            reg = a.get("registered_at") or "—"
            extra = ""
            if a.get("added_by"):
                extra = f" · agregado por `{a['added_by']}`"
            lineas.append(f"{i}. `{cid}` · registrado {reg}{extra}{marca}")

    if not env_lock and actual > 1:
        lineas.append(
            "\n_Para quitar a alguien: `/quitar_admin <chat_id>`._"
        )

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_quitar_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Uso: `/quitar_admin <chat_id>`\n"
            "Mirá los chat_ids con `/admins`.",
            parse_mode="Markdown",
        )
        return

    try:
        objetivo = int(args[0])
    except ValueError:
        await update.message.reply_text(
            f"`{args[0]}` no es un chat_id válido (tiene que ser un número).",
            parse_mode="Markdown",
        )
        return

    if not admin_state.es_admin(objetivo):
        await update.message.reply_text(
            f"`{objetivo}` no figura como admin. Usá `/admins` para ver la lista.",
            parse_mode="Markdown",
        )
        return

    if admin_state._env_override_ids() is not None:
        await update.message.reply_text(
            "La lista de admins está fijada por la env var `ADMIN_CHAT_IDS`. "
            "Editá el `.env` y reiniciá el bot para cambiarla.",
            parse_mode="Markdown",
        )
        return

    quien = update.effective_chat.id
    if admin_state.quitar_admin(objetivo):
        log.warning(
            f"[ADMIN REMOVIDO] chat_id={objetivo} removido_por={quien} "
            f"restantes={admin_state.admin_count()}"
        )
        msg = f"✅ Saqué a `{objetivo}` de la lista de admins."
        if int(objetivo) == int(quien):
            msg += "\n\n_Te quitaste a vos mismo. Si querés volver a entrar y todavía hay cupo, mandá /start de nuevo._"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"No pude quitar a `{objetivo}` (¿ya no estaba?).",
            parse_mode="Markdown",
        )


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

    # En multi-tenant un proceso (= una instancia) atiende N hogares.
    # Lo mostramos para que el admin no confunda "instancia" con "adulto".
    n_hogares = len(hogar_mod.listar_hogares())

    lineas = [
        f"*🗂 Instancias detectadas: {len(instancias)}*",
        f"_{cuenta_verdes} de {len(instancias)} en verde._",
    ]
    if n_hogares > 0:
        lineas.append(
            f"_Atendiendo {n_hogares} hogar(es) multi-tenant — "
            f"detalle en `/hogares`._"
        )
    lineas.append("")

    for i in instancias:
        est = _estado_instancia(i["hbs"], esperados)
        icono = _SEMAFORO[est]
        hb_a = i["hb_aikiu"]
        hb_f = i["hb_familiar"]
        ultimo = _hace(hb_a.get("last_seen") if hb_a else None)
        owner = (hb_a or {}).get("owner_chat_id")
        # En multi-tenant no hay un solo "owner" de la instancia: el proceso
        # atiende a muchos hogares. Lo decimos explícito para no confundir.
        if owner:
            owner_str = f"`{owner}`"
        elif n_hogares > 0:
            owner_str = f"_(multi-tenant: {n_hogares} hogar/es — ver /hogares)_"
        else:
            owner_str = "_(sin adulto registrado)_"

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
    n_hogares = len(hogar_mod.listar_hogares())

    # Headline: peor estado global → emoji + frase
    estados_globales = [_estado_instancia(i["hbs"], esperados) for i in instancias]
    pings_ok = sum(1 for p in (ping_aikiu, ping_admin) if p)  # familiar es opcional
    if "familiar" in esperados:
        pings_ok += 1 if ping_familiar else 0
    pings_total = len(esperados) + 1  # +1 por el admin mismo

    peor_global = _peor(estados_globales) if estados_globales else "ausente"
    icono_g = _SEMAFORO[peor_global]
    sufijo_hogares = f" · {n_hogares} hogar(es)" if n_hogares > 0 else ""
    if peor_global == "verde" and pings_ok == pings_total:
        headline = (
            f"{icono_g} *Todo OK* — {len(instancias)} instancia(s){sufijo_hogares}, "
            f"{pings_ok}/{pings_total} bots respondiendo."
        )
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


def _semaforo_limite(tokens_hoy: int, tpd: Optional[int]) -> tuple[str, str, str]:
    """Devuelve (emoji, descripción corta, porcentaje como string).
    El porcentaje se muestra como '<1%' cuando hay consumo positivo pero
    redondea a 0 (así no parece que no se usó nada).
    Si tpd es None (modelo no catalogado y sin override), devuelve estado
    neutro porque no podemos calcular ratio."""
    if tpd is None or tpd <= 0:
        return ("⚪", "sin límite catalogado", "—")
    ratio = tokens_hoy / tpd
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


def _tpd_efectivo(modelo: str) -> Optional[int]:
    """TPD a usar para los avisos: override de env > catálogo > None."""
    if LIMITE_TOKENS_DIA_OVERRIDE is not None:
        return LIMITE_TOKENS_DIA_OVERRIDE
    return llm_limits.tpd(modelo)


def _modelos_chat_en_uso(d: Path, dias: int = 30) -> list[str]:
    """Lista los modelos de chat (no Whisper) que tuvieron llamadas en los
    últimos N días en esta instancia, ordenados por uso descendente.

    Detectar 'qué LLM se está usando' a partir de los datos reales evita
    asumir cosas: si alguien cambió `modelo_llm` en config.yml, o si
    conviven aikiu + andromarta apuntando a modelos distintos, /llm los
    descubre solos."""
    resumen = usage_mod.resumir(d, dias=dias)
    por_modelo = resumen.get("por_modelo", {})
    chat_models = [
        (m, info["llamadas"])
        for m, info in por_modelo.items()
        if not llm_limits.es_audio(m) and info.get("llamadas", 0) > 0
    ]
    chat_models.sort(key=lambda x: x[1], reverse=True)
    return [m for m, _ in chat_models]


def _tokens_modelo(d: Path, modelo: str, dias: int) -> int:
    """Total de tokens consumidos por un modelo específico en los últimos N días."""
    resumen = usage_mod.resumir(d, dias=dias)
    info = resumen.get("por_modelo", {}).get(modelo, {})
    return int(info.get("total_tokens", 0))


def _formato_limites(modelo: str) -> str:
    """Una línea con los límites free tier del modelo, o '_(no catalogado)_'."""
    lim = llm_limits.limites(modelo)
    if not lim:
        return "_(modelo no catalogado — ver core/llm_limits.py)_"
    partes = []
    if lim.get("rpm") is not None:
        partes.append(f"{lim['rpm']} req/min")
    if lim.get("tpm") is not None:
        partes.append(f"{_formato_tokens(lim['tpm'])} tok/min")
    if lim.get("rpd") is not None:
        partes.append(f"{_formato_tokens(lim['rpd'])} req/día")
    if lim.get("tpd") is not None:
        partes.append(f"{_formato_tokens(lim['tpd'])} tok/día")
    return " · ".join(partes)


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

        lineas.append(f"\n*Instancia `{id_inst}` — {nombre}*")

        # Modelos detectados a partir de los datos reales de los últimos 30
        # días. Si conviven varios (p.ej. aikiu en un modelo y andromarta en
        # otro) los mostramos todos. Si no hay datos todavía, igual mostramos
        # el aviso "sin actividad" abajo.
        modelos = _modelos_chat_en_uso(d, dias=30)

        # Headline por modelo (estado del TPD)
        if not modelos:
            tokens_hoy = chat_hoy["tokens_total"]
            emoji, descr, pct = _semaforo_limite(tokens_hoy, None)
            lineas.append(f"\n{emoji} {_formato_tokens(tokens_hoy)} tokens hoy")
        else:
            for modelo in modelos:
                tokens_hoy_m = _tokens_modelo(d, modelo, dias=1)
                tpd_m = _tpd_efectivo(modelo)
                emoji, descr, pct = _semaforo_limite(tokens_hoy_m, tpd_m)
                fuente_lim = (
                    "override .env"
                    if LIMITE_TOKENS_DIA_OVERRIDE is not None
                    else "free tier Groq"
                )
                if tpd_m is not None:
                    lineas.append(
                        f"\n{emoji} `{modelo}` — {_formato_tokens(tokens_hoy_m)} de "
                        f"{_formato_tokens(tpd_m)} tok hoy ({pct} — _{descr}_, _{fuente_lim}_)"
                    )
                else:
                    lineas.append(
                        f"\n{emoji} `{modelo}` — {_formato_tokens(tokens_hoy_m)} tok hoy "
                        f"_({descr})_"
                    )
                lineas.append(f"   _Límites:_ {_formato_limites(modelo)}")

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

        # Tabla por período (chat agregado, todos los modelos juntos). Bloque
        # monoespaciado para que las columnas se alineen en Telegram.
        lineas.append("\n*Conversación (todos los modelos de chat)*")
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

            # Si la mayoría son rate-limit, el cuello real casi nunca es el
            # TPD diario sino el TPM por minuto. Mostramos los TPM/RPM
            # reales de cada modelo en uso para que el admin entienda contra
            # qué pega. Evita la paradoja de "1% del diario, 83% de errores".
            rate_limit_hits = chat_hoy["errores_por_tipo"].get("rate limit (429)", 0)
            if rate_limit_hits and rate_limit_hits / chat_hoy["error"] >= 0.5:
                # Armamos las pistas modelo a modelo (TPM y RPM del catálogo).
                pistas = []
                for modelo in modelos or []:
                    tpm = llm_limits.tpm(modelo)
                    rpm_v = llm_limits.rpm(modelo)
                    if tpm is None and rpm_v is None:
                        continue
                    bits = []
                    if tpm is not None:
                        bits.append(f"TPM {_formato_tokens(tpm)} tok/min")
                    if rpm_v is not None:
                        bits.append(f"RPM {rpm_v} req/min")
                    pistas.append(f"`{modelo}`: " + ", ".join(bits))
                cuerpo_pistas = (
                    "; ".join(pistas) if pistas else "límites del free tier de Groq por minuto"
                )
                lineas.append(
                    f"_Nota: los 429 casi siempre vienen del cuello por minuto, "
                    f"no del total diario ({cuerpo_pistas}). Pasa cuando hay "
                    f"varias notas de voz seguidas. El servicio se recupera "
                    f"solo cuando baja la ráfaga._"
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
    de conversaciones (eso lo tiene el bot familiar con /aprendizajes y /stats).

    En modo multi-tenant: primero muestra métricas del proceso (uptime, LLM,
    que son globales — un solo Aikiu atiende a todos los hogares) y después
    un bloque por hogar con los datos propios de cada uno (tráfico,
    suscripciones, alertas, disco).
    """
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

    hogares_mt = hogar_mod.listar_hogares()

    lineas: list[str] = ["*🔧 Métricas operativas*\n"]

    # ─────────────────────────────────────────────────────────────────────
    # PARTE A: Métricas POR INSTANCIA (= por proceso). Procesos y LLM son
    # globales en multi-tenant: un solo aikiu atiende a todos los hogares,
    # una sola cuota de Groq.
    # ─────────────────────────────────────────────────────────────────────
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

        # ── 2. LLM: errores y latencias (a nivel proceso — cuota Groq compartida)
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

        lineas.append("🤖 *LLM (Groq) — todos los hogares*")
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

    # ─────────────────────────────────────────────────────────────────────
    # PARTE B: Métricas POR HOGAR (multi-tenant). Tráfico, suscripciones,
    # alertas y disco son específicos de cada adulto.
    # Si no hay hogares (instalación virgen o sin migrar), usamos el
    # directorio de la primera instancia como fallback legacy.
    # ─────────────────────────────────────────────────────────────────────
    dirs_para_metricas_hogar: list[tuple[str, str, Path]] = []
    if hogares_mt:
        for cid in hogares_mt:
            estado = hogar_mod.leer_state(cid)
            nombre_h = (
                estado.get("nombre_adulto_mayor")
                or estado.get("nombre_adulto")
                or f"hogar {cid}"
            )
            dirs_para_metricas_hogar.append(
                (str(cid), nombre_h, hogar_mod.hogar_dir(cid))
            )
    else:
        # Fallback legacy: la primera instancia es el "hogar".
        primero = instancias[0]
        dirs_para_metricas_hogar.append(
            (primero["id"], primero["nombre_adulto"], primero["dir"])
        )

    if hogares_mt:
        lineas.append(f"*🏠 Hogares multi-tenant: {len(hogares_mt)}*\n")

    for id_h, nombre_h, d_h in dirs_para_metricas_hogar:
        if hogares_mt:
            lineas.append(f"*— {nombre_h} (`{id_h}`) —*")

        # ── 3. Volumen de tráfico ────────────────────────────────────────
        serie7d = _serie_mensajes_7d(d_h)
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

        # ── 4. Alertas distress ──────────────────────────────────────────
        alertas_7d = {1: 0, 2: 0, 3: 0}
        for _, s in _stats_dias(d_h, 7):
            dist = s.get("distress", {})
            for nivel in (1, 2, 3):
                alertas_7d[nivel] += int(dist.get(str(nivel), 0))
        total_alertas = sum(alertas_7d.values())
        if total_alertas:
            lineas.append("🚨 *Alertas distress (7d)*")
            lineas.append(
                f"   • Total: {total_alertas}  ·  "
                f"🟡 {alertas_7d[1]} · 🟠 {alertas_7d[2]} · 🔴 {alertas_7d[3]}"
            )
            lineas.append("")

        # ── 5. Suscripciones ─────────────────────────────────────────────
        n_familiares = _contar_familiares(d_h)
        lineas.append("👥 *Suscripciones*")
        lineas.append(f"   • Familiares vinculados: {n_familiares}")
        lineas.append("")

        # ── 6. Disco ─────────────────────────────────────────────────────
        tam_logs, n_logs = _tamano_logs(d_h)
        tam_stats = (d_h / "stats.json").stat().st_size if (d_h / "stats.json").exists() else 0
        tam_recep = (d_h / "receptividad.json").stat().st_size if (d_h / "receptividad.json").exists() else 0
        tam_perfil = (d_h / "perfil.md").stat().st_size if (d_h / "perfil.md").exists() else 0
        lineas.append("💾 *Disco*")
        lineas.append(f"   • logs/: {_formato_bytes(tam_logs)} en {n_logs} archivo(s)")
        lineas.append(
            f"   • stats: {_formato_bytes(tam_stats)}  ·  "
            f"perfil: {_formato_bytes(tam_perfil)}  ·  "
            f"receptividad: {_formato_bytes(tam_recep)}"
        )
        lineas.append("")

        # ── 7. Salud de archivos ─────────────────────────────────────────
        salud = _salud_archivos(d_h)
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
# /hogares  +  /borrar
# ---------------------------------------------------------------------------

def _info_hogar(chat_id: int) -> dict:
    """Datos relevantes de un hogar para mostrar al admin."""
    d = hogar_mod.hogar_dir(chat_id)
    estado = hogar_mod.leer_state(chat_id)
    fams = load_json(hogar_mod.familiares_path(chat_id), default=[])
    stats = load_json(hogar_mod.stats_path(chat_id), default={})

    ultimo_dia = sorted(stats.keys(), reverse=True)[0] if stats else None
    msgs_ult = stats.get(ultimo_dia, {}).get("mensajes", 0) if ultimo_dia else 0

    perfil_p = hogar_mod.perfil_path(chat_id)
    perfil_kb = perfil_p.stat().st_size // 1024 if perfil_p.exists() else 0

    nombre_raw = estado.get("nombre_adulto") or estado.get("nombre_adulto_mayor")
    if nombre_raw:
        nombre_md = f"*{_escape_md(nombre_raw)}*"
    else:
        nombre_md = "_(sin nombre)_"

    return {
        "chat_id": chat_id,
        "dir": d,
        "nombre_md": nombre_md,
        "alta": estado.get("registered_at", "—"),
        "migrated": estado.get("migrated_from_legacy", False),
        "familiares": len(fams),
        "ultimo_dia": ultimo_dia or "—",
        "msgs_ultimo_dia": msgs_ult,
        "perfil_kb": perfil_kb,
    }


async def cmd_hogares(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista los hogares multi-tenant registrados.

    A diferencia de /instancias (que mira heartbeats de procesos),
    /hogares mira el `instances/` del registry y muestra cada adulto que
    tiene su carpeta creada — usalo para auditar quién está usando el
    sistema y para decidir qué borrar."""
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    ids = hogar_mod.listar_hogares()
    if not ids:
        await _reply_md_safe(
            update.message,
            "*🏠 Hogares*\n\nNo hay hogares registrados todavía.\n"
            "_Cualquiera que mande /start al bot principal va a crear el suyo._",
        )
        return

    lineas = [f"*🏠 Hogares registrados: {len(ids)}*\n"]
    for cid in ids:
        info = _info_hogar(cid)
        marca_mig = " · _(migrado del legacy)_" if info["migrated"] else ""
        lineas.append(f"{info['nombre_md']} — `{cid}`{marca_mig}")
        lineas.append(f"   • Alta: {info['alta']}")
        lineas.append(
            f"   • Familiares vinculados: {info['familiares']}"
        )
        lineas.append(
            f"   • Actividad ({info['ultimo_dia']}): {info['msgs_ultimo_dia']} mensajes"
        )
        if info["perfil_kb"]:
            lineas.append(f"   • Perfil: {info['perfil_kb']} KB")
        lineas.append("")

    lineas.append("Para eliminar un hogar usá `/borrar <chat_id>` (pide confirmación).")
    await _reply_md_safe(update.message, "\n".join(lineas))


async def cmd_borrar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Borra el directorio de un hogar.

    Flujo en dos pasos para evitar accidentes:
    - `/borrar <chat_id>`           → muestra info y pide confirmación.
    - `/borrar <chat_id> CONFIRMAR` → ejecuta el borrado físico (rm -rf).

    El borrado NO se puede deshacer. Borra `instances/<chat_id>/`
    completo: state, perfil, stats, logs, todo.
    """
    if not _es_admin_autorizado(update.effective_chat.id):
        await _rechazar_silencioso(update, "no es admin")
        return

    args = context.args or []
    if not args:
        await _reply_md_safe(
            update.message,
            "Uso: `/borrar <chat_id>` (te muestro qué se borraría).\n"
            "Después: `/borrar <chat_id> CONFIRMAR` para ejecutar.",
        )
        return

    try:
        objetivo = int(args[0])
    except ValueError:
        await _reply_md_safe(
            update.message,
            f"`{args[0]}` no es un chat_id válido (tiene que ser un número).",
        )
        return

    if not hogar_mod.existe_hogar(objetivo):
        await _reply_md_safe(
            update.message,
            f"No encontré un hogar con chat_id `{objetivo}`. "
            f"Mirá la lista con `/hogares`.",
        )
        return

    confirma = len(args) >= 2 and args[1].strip().upper() == "CONFIRMAR"
    info = _info_hogar(objetivo)

    if not confirma:
        await _reply_md_safe(
            update.message,
            f"⚠️ *Vas a borrar el hogar `{objetivo}`*\n\n"
            f"• Adulto: {info['nombre_md']}\n"
            f"• Alta: {info['alta']}\n"
            f"• Familiares vinculados: {info['familiares']}\n"
            f"• Perfil: {info['perfil_kb']} KB\n"
            f"• Directorio: `{info['dir']}`\n\n"
            f"Esto borra TODO (state, perfil, stats, logs, familiares) y "
            f"es irreversible. Si estás seguro:\n\n"
            f"`/borrar {objetivo} CONFIRMAR`",
        )
        return

    quien = update.effective_chat.id
    if hogar_mod.borrar_hogar(objetivo):
        # Limpieza de huérfanos derivados del borrado:
        # - Invitaciones pendientes del hogar (códigos vivos que apuntaban
        #   a un adulto que ya no existe).
        # - Adulto activo en `_familiar_state.json` de cualquier familiar
        #   que lo tuviera como default (lo reasignamos a otro vínculo).
        codigos_purgados = invites_mod.purgar_de_hogar(objetivo)
        familiares_reasignados = fam_state_mod.limpiar_hogar_borrado(objetivo)
        log.warning(
            f"[HOGAR BORRADO] chat_id={objetivo} borrado_por={quien} "
            f"codigos_purgados={codigos_purgados} "
            f"familiares_reasignados={familiares_reasignados} "
            f"hora={datetime.now().isoformat(timespec='seconds')}"
        )
        extras = []
        if codigos_purgados:
            extras.append(
                f"{codigos_purgados} código(s) de invitación pendiente(s) limpiados"
            )
        if familiares_reasignados:
            extras.append(
                f"{familiares_reasignados} familiar(es) reasignado(s) a otro adulto"
            )
        extras_txt = ("\n_" + "; ".join(extras) + "._") if extras else ""
        await _reply_md_safe(
            update.message,
            f"✅ Listo, borré el hogar `{objetivo}` ({info['nombre_md']}).{extras_txt}\n"
            f"_Si el adulto vuelve a mandar /start, se le crea uno nuevo desde cero._",
        )
    else:
        await _reply_md_safe(
            update.message,
            f"❌ No pude borrar `{objetivo}`. Mirá los logs del admin.",
        )


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

    # `aikiu.log` se escribe en `BASE_DIR/aikiu.log` (raíz del repo), porque
    # es del proceso, no del hogar. En modo single-instance `d == BASE_DIR`
    # y ambos paths coinciden. En modo multi-tenant con AIKIU_REGISTRY,
    # `d` es `<registry>/<instance_id>/` (que no tiene el log) → fallback
    # a BASE_DIR.
    log_path = d / "aikiu.log"
    if not log_path.exists():
        log_path = BASE_DIR / "aikiu.log"

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
    app.add_handler(CommandHandler("hogares", cmd_hogares))
    app.add_handler(CommandHandler("borrar", cmd_borrar))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("admins", cmd_admins))
    app.add_handler(CommandHandler("quitar_admin", cmd_quitar_admin))

    log.info("Bot admin iniciando...")
    cupo = admin_state.admins_max()
    if not admin_state.tiene_admin():
        log.warning(
            f"Todavía no hay admins registrados (cupo {cupo}). Apenas el bot "
            f"esté arriba, los integrantes del equipo mandan /start desde su "
            f"Telegram para sumarse hasta llenar el cupo."
        )
    else:
        ids = admin_state.admin_chat_ids()
        log.info(f"Admins registrados: {len(ids)}/{cupo} → {ids}")

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
        hb_mod.iniciar_heartbeat("admin", dir_override=ADMIN_DIR)
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
