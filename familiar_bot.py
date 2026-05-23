"""
Bot familiar — múltiples adultos por familiar (many-to-many).

Cada familiar que llega al bot manda `/start` y se da de alta. Después se
vincula a uno o más adultos con `/vincular <CODIGO>` (el código se genera
en el bot del adulto con `/invitar`).

Si el familiar tiene un solo adulto, todos los comandos operan sobre él
automáticamente. Si tiene varios, elige cuál con `/elegir <chat_id>` (o se
lo pedimos cuando ejecute un comando que necesita un adulto y el activo
no esté seteado).

Comandos legacy (`/perfil`, `/stats`, `/aprendizajes`, `/mensaje`, `/editar`,
`/suscriptores`, `/nombre`) siguen funcionando: leen del adulto activo.

Para retrocompatibilidad con instalaciones single-tenant y la suite de
tests existente, los atributos `FAMILIARES_PATH`, `PERFIL_PATH` y
`STATS_PATH` siguen apuntando a la raíz del repo y las funciones
`cargar_familiares()`, `agregar_familiar()`, `actualizar_nombre()` y
`es_suscriptor()` siguen operando sobre `FAMILIARES_PATH`.

En multi-tenant, la fuente de verdad de los familiares vinculados a un
adulto es `instances/<adulto>/familiares.json`.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from groq import AsyncGroq
from telegram import Bot, BotCommand, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ConversationHandler,
    MessageHandler, filters, ContextTypes,
)

from core.tts import sintetizar
from core import state as state_mod
from core import heartbeat as hb_mod
from core import usage as usage_mod
from core import hogar as hogar_mod
from core import familiar_state as fam_state
from core import invites as invites_mod
from core.utils import norm, load_json, write_json_atomic, write_text_atomic

BASE_DIR         = Path(__file__).parent
PERFIL_PATH      = BASE_DIR / "perfil.md"          # legacy fallback
FAMILIARES_PATH  = BASE_DIR / "familiares.json"    # legacy fallback
STATS_PATH       = BASE_DIR / "stats.json"         # legacy fallback

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] familiar %(message)s",
)
log = logging.getLogger("aikiu-familiar")

FAMILIAR_TOKEN = os.environ.get("FAMILIAR_BOT_TOKEN", "")
ADULTO_BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")


def _cargar_config() -> dict:
    cfg_path = BASE_DIR / "config.yml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

_CONFIG = _cargar_config()
VOZ_TTS = _CONFIG.get("voz_tts", "es-AR-ElenaNeural")


def _nombre_adulto_global() -> str:
    """Nombre por default del adulto (template global). Solo se usa cuando
    no hay un adulto activo / hogar específico (modo legacy)."""
    return _CONFIG.get("nombre_adulto_mayor", "Marta")


def _nombre_adulto_de(chat_id_adulto: Optional[int]) -> str:
    if chat_id_adulto is None:
        return _nombre_adulto_global()
    estado = hogar_mod.leer_state(chat_id_adulto)
    nombre = estado.get("nombre_adulto_mayor") or estado.get("nombre_adulto")
    return nombre or _nombre_adulto_global()


# Compat con tests viejos que llaman a `_nombre_adulto()` directamente.
_nombre_adulto = _nombre_adulto_global


ELIGIENDO, RECIBIENDO, ESPERANDO_MENSAJE = range(3)

# Lista que Telegram muestra en el boton de menu azul al lado de la caja de texto.
COMANDOS_TELEGRAM = [
    BotCommand("vincular",      "Vincular este familiar a un adulto con codigo"),
    BotCommand("misadultos",    "Listar los adultos a los que estas vinculado"),
    BotCommand("elegir",        "Fijar el adulto activo (cuando tenes varios)"),
    BotCommand("mensaje",       "Enviarle un mensaje al adulto (texto o voz)"),
    BotCommand("nombre",        "Registrar como te conoce el adulto"),
    BotCommand("perfil",        "Ver el perfil completo del adulto activo"),
    BotCommand("editar",        "Editar una seccion del perfil"),
    BotCommand("stats",         "Actividad del adulto en los ultimos dias"),
    BotCommand("aprendizajes",  "Lo que Clara aprendio del adulto"),
    BotCommand("suscriptores",  "Familiares vinculados al adulto activo"),
    BotCommand("ayuda",         "Menu de comandos"),
]

SECCIONES = [
    "Quién es",
    "Familia y contactos cercanos",
    "Gustos y temas que la alegran",
    "Salud (para contexto, no para diagnosticar)",
    "Temas a manejar con cuidado",
    "Reglas del asistente",
]


# ---------------------------------------------------------------------------
# Helpers legacy (preservan la firma vieja para tests/instalaciones single-tenant)
# ---------------------------------------------------------------------------

def cargar_familiares() -> list[dict]:
    """Lee el `familiares.json` legacy de la raíz."""
    return load_json(FAMILIARES_PATH, default=[])


def guardar_familiares(familiares: list[dict]):
    write_json_atomic(FAMILIARES_PATH, familiares)


def es_suscriptor(chat_id: int) -> bool:
    """True si chat_id está en el `familiares.json` legacy O vinculado a algún hogar."""
    if any(f["chat_id"] == chat_id for f in cargar_familiares()):
        return True
    # En multi-tenant también lo consideramos suscriptor si está vinculado
    # a al menos un adulto.
    return bool(fam_state.adultos_de(chat_id))


def agregar_familiar(chat_id: int) -> bool:
    """Agrega al `familiares.json` legacy. Devuelve True si era nuevo."""
    familiares = cargar_familiares()
    if not any(f["chat_id"] == chat_id for f in familiares):
        familiares.append({"chat_id": chat_id, "nombre": ""})
        guardar_familiares(familiares)
        return True
    return False


def actualizar_nombre(chat_id: int, nombre: str):
    """Actualiza el nombre del familiar en el `familiares.json` legacy."""
    familiares = cargar_familiares()
    for f in familiares:
        if f["chat_id"] == chat_id:
            f["nombre"] = nombre.strip()
            guardar_familiares(familiares)
            return
    familiares.append({"chat_id": chat_id, "nombre": nombre.strip()})
    guardar_familiares(familiares)


def nombre_registrado(chat_id: int, fallback: str = "Tu familiar") -> str:
    """Nombre del familiar. Mira legacy primero, después multi-tenant."""
    for f in cargar_familiares():
        if f["chat_id"] == chat_id:
            return f["nombre"] or fallback
    nombre = fam_state.nombre_de(chat_id, fallback="")
    return nombre or fallback


# ---------------------------------------------------------------------------
# Resolución del adulto activo del familiar
# ---------------------------------------------------------------------------

def _adulto_activo_o_legacy(chat_id_familiar: int) -> Optional[int]:
    """
    Devuelve el chat_id del adulto sobre el que opera el familiar:

    - Multi-tenant: el adulto activo del familiar (o el único, si tiene uno).
    - Legacy fallback: si el familiar no tiene ningún adulto vinculado pero
      hay un `state_mod.owner_chat_id()` registrado (instalación vieja),
      devolvemos ese para que los comandos legacy sigan funcionando.

    Devuelve None solo si el familiar tiene 2+ adultos y no eligió, o si no
    hay ningún adulto disponible en el sistema.
    """
    activo = fam_state.adulto_activo(chat_id_familiar)
    if activo is not None:
        return activo
    vinculados = fam_state.adultos_de(chat_id_familiar)
    if len(vinculados) >= 2:
        return None  # ambiguo, hay que elegir
    return state_mod.owner_chat_id()


def _perfil_path_para(chat_id_adulto: Optional[int]) -> Path:
    return hogar_mod.perfil_path(chat_id_adulto) if chat_id_adulto is not None else PERFIL_PATH


def _stats_path_para(chat_id_adulto: Optional[int]) -> Path:
    return hogar_mod.stats_path(chat_id_adulto) if chat_id_adulto is not None else STATS_PATH


def _familiares_path_para(chat_id_adulto: Optional[int]) -> Path:
    return hogar_mod.familiares_path(chat_id_adulto) if chat_id_adulto is not None else FAMILIARES_PATH


# ---------------------------------------------------------------------------
# Lectura/escritura del perfil del adulto activo
# ---------------------------------------------------------------------------

def leer_perfil(chat_id_adulto: Optional[int] = None) -> str:
    path = _perfil_path_para(chat_id_adulto)
    return path.read_text(encoding="utf-8") if path.exists() else "(Sin perfil cargado aún)"


def leer_seccion(nombre: str, chat_id_adulto: Optional[int] = None) -> str:
    match = re.search(
        rf'## {re.escape(nombre)}\n(.*?)(?=\n## |\Z)',
        leer_perfil(chat_id_adulto), re.DOTALL
    )
    return match.group(1).strip() if match else "(sección no encontrada)"


def actualizar_seccion(nombre: str, nuevo: str, chat_id_adulto: Optional[int] = None):
    path = _perfil_path_para(chat_id_adulto)
    nuevo_content = re.sub(
        rf'(## {re.escape(nombre)}\n)(.*?)(?=\n## |\Z)',
        lambda m: f"{m.group(1)}{nuevo.strip()}\n\n",
        leer_perfil(chat_id_adulto), flags=re.DOTALL
    )
    write_text_atomic(path, nuevo_content)


# ---------------------------------------------------------------------------
# Gate genérico de autorización
# ---------------------------------------------------------------------------

async def _pedir_start(update: Update) -> None:
    await update.message.reply_text("Mandá /start para registrarte.")


async def _pedir_elegir_adulto(update: Update, vinculados: list[int]) -> None:
    nombres = []
    for a in vinculados:
        nombres.append(f"`/elegir {a}` — {_nombre_adulto_de(a)}")
    listado = "\n".join(nombres)
    await update.message.reply_text(
        f"Estás vinculado a varios adultos. Elegí sobre cuál querés operar:\n\n{listado}",
        parse_mode="Markdown",
    )


async def _pedir_vincular(update: Update) -> None:
    await update.message.reply_text(
        "Todavía no estás vinculado a ningún adulto.\n"
        "Pedile el código de invitación al adulto (lo genera con `/invitar` "
        "en el bot principal) y mandá: `/vincular <CODIGO>`",
        parse_mode="Markdown",
    )


def _resolver_adulto_o_explicar_async_handler(chat_id_familiar: int):
    """Devuelve (chat_id_adulto, status) — status indica qué pedirle al
    familiar si no se pudo resolver. status: 'ok', 'pedir_vincular',
    'pedir_elegir'.

    Reglas:
    1. Si tiene adulto activo → operar sobre ese.
    2. Si tiene 2+ vínculos sin activo → pedir elegir.
    3. Si tiene un único vínculo → ese es el activo (lo deriva `adulto_activo`).
    4. Si no tiene vínculos multi-tenant pero hay `owner_chat_id()` legacy →
       operar sobre el owner (instalación single-tenant migrada).
    5. Si no tiene vínculos y NO hay owner legacy:
       - Si existen hogares registrados (multi-tenant en uso) → pedir vincular.
       - Si no hay hogares (modo legacy puro / tests aislados) → operar en
         modo legacy con `adulto_id=None` (paths globales del repo).
    """
    activo = fam_state.adulto_activo(chat_id_familiar)
    if activo is not None:
        return activo, "ok"
    vinculados = fam_state.adultos_de(chat_id_familiar)
    if len(vinculados) >= 2:
        return None, "pedir_elegir"
    legacy_owner = state_mod.owner_chat_id()
    if legacy_owner is not None:
        return legacy_owner, "ok"
    try:
        hay_hogares = bool(hogar_mod.listar_hogares())
    except Exception:
        hay_hogares = False
    if hay_hogares:
        return None, "pedir_vincular"
    return None, "ok"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    raw_first = getattr(update.effective_user, "first_name", None) if update.effective_user else None
    nombre_tg = raw_first if isinstance(raw_first, str) and raw_first else "familiar"

    # ¿Estaba ya registrado (legacy O multi-tenant)? Lo determinamos antes
    # de tocar nada, porque `agregar_familiar` también devuelve False si ya
    # estaba en el legacy.
    ya_estaba_legacy = any(f["chat_id"] == chat_id for f in cargar_familiares())
    ya_estaba_mt = bool(fam_state.leer_estado(chat_id))
    era_nuevo = not (ya_estaba_legacy or ya_estaba_mt)

    # Compat con tests viejos: también damos de alta en familiares.json legacy.
    agregar_familiar(chat_id)
    fam_state.asegurar_familiar(chat_id, nombre=nombre_tg)

    # ¿Tiene nombre registrado en el legacy?
    nombre_legacy = next(
        (f["nombre"] for f in cargar_familiares() if f["chat_id"] == chat_id),
        "",
    )

    vinculados = fam_state.adultos_de(chat_id)
    if vinculados:
        nombres = ", ".join(_nombre_adulto_de(a) for a in vinculados)
        cuerpo_vinculos = (
            f"Estás vinculado a: *{nombres}*.\n"
            "Usá /misadultos para verlos."
        )
    else:
        cuerpo_vinculos = (
            "Para vincularte a un adulto, pedile el código de invitación "
            "(lo genera con `/invitar` en su bot) y mandá: `/vincular <CODIGO>`."
        )

    menu = (
        "Comandos disponibles:\n"
        "/vincular — vincularte a un adulto con código\n"
        "/misadultos — ver tus adultos vinculados\n"
        "/elegir — fijar el adulto activo\n"
        "/mensaje — enviarle un mensaje al adulto\n"
        "/nombre — registrar cómo te conoce\n"
        "/perfil — ver el perfil del adulto\n"
        "/editar — editar una sección del perfil\n"
        "/stats — actividad de los últimos días\n"
        "/aprendizajes — lo que Clara aprendió\n"
        "/suscriptores — ver quién recibe alertas\n"
        "/ayuda — ver este menú"
    )

    if era_nuevo:
        encabezado = f"Hola {nombre_tg}, quedaste registrado."
        log.info(f"Nuevo familiar: chat_id={chat_id} nombre={nombre_tg!r}")
    else:
        encabezado = f"Hola {nombre_tg}, ya estabas registrado."

    cuerpo_nombre = ""
    if not nombre_legacy:
        cuerpo_nombre = "Si querés contarme cómo te llamás, usá /nombre TuNombre.\n\n"

    await update.message.reply_text(
        f"{encabezado}\n\n{cuerpo_vinculos}\n\n{cuerpo_nombre}{menu}",
        parse_mode="Markdown",
    )


async def cmd_vincular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id) and not fam_state.leer_estado(chat_id):
        await _pedir_start(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "Uso: `/vincular <CODIGO>`\n"
            "El código se lo pedís al adulto: él lo genera con `/invitar`.",
            parse_mode="Markdown",
        )
        return
    codigo = args[0].strip().upper()
    adulto_id = invites_mod.consumir(codigo)
    if adulto_id is None:
        await update.message.reply_text(
            f"El código `{codigo}` no es válido, expiró o apunta a un hogar "
            "que ya no existe. Pedile uno nuevo al adulto.",
            parse_mode="Markdown",
        )
        return

    nombre_fam = fam_state.nombre_de(chat_id, fallback="")
    if not fam_state.vincular(chat_id, adulto_id, nombre=nombre_fam):
        # No pude vincular (caso poco probable: el hogar dejó de existir
        # entre `consumir` y `vincular`, o un error de IO). Como
        # `consumir` ya descontó el código, lo único que podemos hacer
        # es avisarle al familiar para que pida uno nuevo.
        log.warning(
            f"Vinculación fallida: familiar {chat_id} ↔ adulto {adulto_id} "
            f"(hogar dejó de existir o error de IO)"
        )
        await update.message.reply_text(
            "No pude vincularte: el hogar al que apuntaba el código ya no "
            "existe. Pedile al adulto que te genere un código nuevo con "
            "`/invitar`.",
            parse_mode="Markdown",
        )
        return

    log.info(f"Vinculación: familiar {chat_id} ↔ adulto {adulto_id}")
    await update.message.reply_text(
        f"Listo, quedaste vinculado a *{_nombre_adulto_de(adulto_id)}*. "
        f"Desde ahora vas a recibir sus alertas y podés usar los comandos "
        f"como /perfil, /stats, etc.",
        parse_mode="Markdown",
    )


async def cmd_misadultos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id) and not fam_state.leer_estado(chat_id):
        await _pedir_start(update)
        return
    vinculados = fam_state.adultos_de(chat_id)
    if not vinculados:
        await _pedir_vincular(update)
        return
    activo = fam_state.adulto_activo(chat_id)
    lineas = ["*Tus adultos vinculados:*\n"]
    for a in vinculados:
        marca = " ← _activo_" if a == activo else ""
        lineas.append(f"• `{a}` — {_nombre_adulto_de(a)}{marca}")
    if len(vinculados) > 1:
        lineas.append("\n_Cambiá el activo con `/elegir <chat_id>`._")
    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_elegir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id) and not fam_state.leer_estado(chat_id):
        await _pedir_start(update)
        return
    args = context.args or []
    vinculados = fam_state.adultos_de(chat_id)
    if not args:
        if not vinculados:
            await _pedir_vincular(update)
            return
        await _pedir_elegir_adulto(update, vinculados)
        return
    try:
        objetivo = int(args[0])
    except ValueError:
        await update.message.reply_text("El argumento tiene que ser un chat_id (número).")
        return
    if objetivo not in vinculados:
        await update.message.reply_text(
            f"No estás vinculado al adulto `{objetivo}`. Usá /misadultos para ver tus vínculos.",
            parse_mode="Markdown",
        )
        return
    fam_state.setear_adulto_activo(chat_id, objetivo)
    await update.message.reply_text(
        f"Listo, ahora opera sobre *{_nombre_adulto_de(objetivo)}* (`{objetivo}`).",
        parse_mode="Markdown",
    )


async def cmd_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    nombre_arg = " ".join(context.args).strip() if context.args else ""

    if not nombre_arg:
        actual = nombre_registrado(chat_id, fallback="")
        adulto_nombre = _nombre_adulto_de(adulto_id) if adulto_id else _nombre_adulto_global()
        if actual:
            await update.message.reply_text(
                f"Tu nombre para {adulto_nombre} es: *{actual}*\n\n"
                "Para cambiarlo: /nombre NuevoNombre",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "Todavía no registraste tu nombre.\nUsá: /nombre Germán"
            )
        return

    actualizar_nombre(chat_id, nombre_arg)             # legacy
    fam_state.actualizar_nombre(chat_id, nombre_arg)   # multi-tenant
    # Si está vinculado a un adulto, también actualizamos el nombre en el
    # familiares.json del hogar para que las alertas lo identifiquen bien.
    if adulto_id is not None:
        fam_state.vincular(chat_id, adulto_id, nombre=nombre_arg)
    log.info(f"Nombre registrado: {chat_id} → '{nombre_arg}'")
    adulto_nombre = _nombre_adulto_de(adulto_id) if adulto_id else _nombre_adulto_global()
    await update.message.reply_text(
        f"Listo, cuando le mandes mensajes a {adulto_nombre} vas a aparecer como *{nombre_arg}*.",
        parse_mode="Markdown",
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id) and not fam_state.leer_estado(chat_id):
        await _pedir_start(update)
        return
    adulto_id, _ = _resolver_adulto_o_explicar_async_handler(chat_id)
    nombre = _nombre_adulto_de(adulto_id) if adulto_id else _nombre_adulto_global()
    await update.message.reply_text(
        "*Comandos disponibles:*\n\n"
        "/vincular — vincularte a un adulto\n"
        "/misadultos — ver tus adultos\n"
        "/elegir — fijar el adulto activo\n"
        f"/mensaje — enviarle un mensaje a {nombre} (texto o nota de voz)\n"
        f"/nombre — registrar cómo te conoce {nombre}\n"
        "/perfil — ver el perfil completo\n"
        "/editar — editar una sección del perfil\n"
        "/stats — actividad de los últimos días\n"
        f"/aprendizajes — lo que Clara aprendió de {nombre}\n"
        "/suscriptores — lista de familiares registrados\n"
        "/cancelar — cancela la operación en curso",
        parse_mode="Markdown"
    )


async def cmd_suscriptores(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return

    if adulto_id is None:
        familiares = cargar_familiares()
    else:
        familiares = load_json(_familiares_path_para(adulto_id), default=[])
    if not familiares:
        await update.message.reply_text("No hay familiares registrados.")
        return
    lineas = [f"*Familiares de {_nombre_adulto_de(adulto_id)}: {len(familiares)}*\n"]
    for f in familiares:
        nombre = f.get("nombre") or "(sin nombre)"
        lineas.append(f"• {nombre} — ID: {f['chat_id']}")
    await update.message.reply_text(
        "\n".join(lineas),
        parse_mode="Markdown"
    )


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return
    perfil = leer_perfil(adulto_id)
    for i in range(0, len(perfil), 4000):
        await update.message.reply_text(f"```\n{perfil[i:i+4000]}\n```", parse_mode="Markdown")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return

    adulto_nombre = _nombre_adulto_de(adulto_id)
    stats_path = _stats_path_para(adulto_id)
    if not stats_path.exists():
        await update.message.reply_text("Todavía no hay estadísticas registradas.")
        return
    stats = load_json(stats_path)
    if not stats:
        await update.message.reply_text("Error al leer las estadísticas.")
        return

    dias = sorted(stats.keys(), reverse=True)[:7]
    if not dias:
        await update.message.reply_text("Sin datos aún.")
        return

    lineas = [f"📊 *Actividad de {adulto_nombre} — últimos días*\n"]
    for dia in dias:
        d = stats[dia]
        mensajes = d.get("mensajes", 0)
        primero  = d.get("primer_mensaje", "—")
        ultimo   = d.get("ultimo_mensaje", "—")
        distress = d.get("distress", {})
        alertas  = sum(int(distress.get(str(n), 0)) for n in [1, 2, 3])
        an       = d.get("analisis_nocturno", {})
        aprendizajes = an.get("aprendizajes_nuevos", "—")

        linea = f"📅 *{dia}*: {mensajes} msg · {primero}–{ultimo}"
        if alertas:
            linea += f" · ⚠️ {alertas} alerta(s)"
        if isinstance(aprendizajes, int) and aprendizajes > 0:
            linea += f" · 💡 {aprendizajes} aprendizaje(s)"
        lineas.append(linea)

    await update.message.reply_text("\n".join(lineas), parse_mode="Markdown")


async def cmd_aprendizajes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return

    adulto_nombre = _nombre_adulto_de(adulto_id)
    perfil = leer_perfil(adulto_id)
    aprendizajes = re.search(r"## Aprendizajes\n(.*?)(?=\n## |\Z)", perfil, re.DOTALL)
    ajustes = re.search(r"## Ajustes sugeridos\n(.*?)(?=\n## |\Z)", perfil, re.DOTALL)

    texto = f"🧠 *Lo que Clara aprendió sobre {adulto_nombre}*\n\n"
    if aprendizajes and aprendizajes.group(1).strip():
        texto += aprendizajes.group(1).strip()
    else:
        texto += "_(sin aprendizajes registrados aún)_"

    if ajustes and ajustes.group(1).strip():
        texto += f"\n\n💬 *Ajustes sugeridos para la conversación*\n\n{ajustes.group(1).strip()}"

    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_editar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return ConversationHandler.END
    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return ConversationHandler.END
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return ConversationHandler.END

    context.user_data["adulto_id"] = adulto_id
    keyboard = [[s] for s in SECCIONES] + [["❌ Cancelar"]]
    lista = "\n".join(f"• {s}" for s in SECCIONES)
    await update.message.reply_text(
        f"¿Qué sección de *{_nombre_adulto_de(adulto_id)}* querés editar? "
        f"Tocá un botón o escribí el nombre exacto:\n\n{lista}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ELIGIENDO


_SECCIONES_NORM = {norm(s): s for s in SECCIONES}


async def elegir_seccion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "❌ Cancelar":
        await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    seccion = _SECCIONES_NORM.get(norm(texto))
    if not seccion:
        await update.message.reply_text("Elegí una opción de la lista.")
        return ELIGIENDO
    context.user_data["seccion"] = seccion
    adulto_id = context.user_data.get("adulto_id")
    actual = leer_seccion(texto, chat_id_adulto=adulto_id)
    await update.message.reply_text(
        f"*Sección: {texto}*\n\nContenido actual:\n```\n{actual}\n```\n\n"
        "Enviá el nuevo contenido. Cada ítem en una línea con guión:\n"
        "`- Ítem uno`\n`- Ítem dos`\n\n/cancelar para salir sin guardar.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return RECIBIENDO


async def recibir_contenido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    seccion = context.user_data["seccion"]
    adulto_id = context.user_data.get("adulto_id")
    actualizar_seccion(seccion, update.message.text.strip(), chat_id_adulto=adulto_id)
    log.info(f"Sección '{seccion}' actualizada por {update.effective_chat.id} (adulto={adulto_id})")
    await update.message.reply_text(
        f"✓ *{seccion}* actualizada. Clara lo tendrá en cuenta desde la próxima conversación.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Puente familiar (/mensaje)
# ---------------------------------------------------------------------------

async def cmd_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not es_suscriptor(chat_id):
        await _pedir_start(update)
        return ConversationHandler.END
    if not ADULTO_BOT_TOKEN:
        await update.message.reply_text("Error: BOT_TOKEN del adulto no configurado.")
        return ConversationHandler.END

    adulto_id, status = _resolver_adulto_o_explicar_async_handler(chat_id)
    if status == "pedir_elegir":
        await _pedir_elegir_adulto(update, fam_state.adultos_de(chat_id))
        return ConversationHandler.END
    if status == "pedir_vincular":
        await _pedir_vincular(update)
        return ConversationHandler.END
    if adulto_id is None:
        adulto_nombre = _nombre_adulto_global()
        await update.message.reply_text(
            f"Todavía {adulto_nombre} no abrió el bot."
        )
        return ConversationHandler.END

    context.user_data["adulto_id"] = adulto_id
    adulto_nombre = _nombre_adulto_de(adulto_id)
    await update.message.reply_text(
        f"Enviá tu mensaje para {adulto_nombre} (texto o nota de voz). /cancelar para salir."
    )
    return ESPERANDO_MENSAJE


async def recibir_mensaje_familiar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    raw_adulto_id = (
        context.user_data.get("adulto_id")
        if isinstance(context.user_data, dict)
        else None
    )
    adulto_id = raw_adulto_id if isinstance(raw_adulto_id, int) else None
    if adulto_id is None:
        # Salvavidas: recuperar adulto activo si se perdió el state de la conv.
        adulto_id, _ = _resolver_adulto_o_explicar_async_handler(chat_id)
    adulto_nombre = _nombre_adulto_de(adulto_id) if adulto_id else _nombre_adulto_global()

    raw_first = getattr(update.effective_user, "first_name", None) if update.effective_user else None
    fallback_first = raw_first if isinstance(raw_first, str) and raw_first else "Tu familiar"
    nombre = nombre_registrado(chat_id, fallback=fallback_first)

    # Obtener el texto: desde voz o texto plano
    if update.message.voice:
        if not GROQ_API_KEY:
            await update.message.reply_text("Error: GROQ_API_KEY no configurada para transcribir audio.")
            return ConversationHandler.END
        try:
            groq = AsyncGroq(api_key=GROQ_API_KEY)
            with tempfile.TemporaryDirectory() as tmp:
                ogg = Path(tmp) / "familiar.ogg"
                archivo = await update.message.voice.get_file()
                await archivo.download_to_drive(ogg)
                bytes_audio = ogg.stat().st_size if ogg.exists() else 0
                async with usage_mod.timed_stt("whisper-large-v3", bytes_audio):
                    with open(ogg, "rb") as f:
                        result = await groq.audio.transcriptions.create(
                            file=(ogg.name, f, "audio/ogg"),
                            model="whisper-large-v3",
                            language="es",
                            response_format="text",
                        )
            texto = result.strip() if isinstance(result, str) else result.text.strip()
            log.info(f"Transcripción de familiar: '{texto}'")
        except Exception as e:
            log.error(f"Error transcribiendo audio: {e}")
            await update.message.reply_text("No pude transcribir el audio. Probá mandando texto.")
            return ESPERANDO_MENSAJE
    else:
        texto = update.message.text.strip()

    if not texto:
        await update.message.reply_text("No entendí el mensaje. Intentá de nuevo.")
        return ESPERANDO_MENSAJE

    mensaje_para_adulto = f"{nombre} te manda a decir: {texto}"

    if adulto_id is None:
        await update.message.reply_text(
            f"Todavía {adulto_nombre} no abrió el bot."
        )
        return ConversationHandler.END

    try:
        async with Bot(token=ADULTO_BOT_TOKEN) as adulto_bot:
            if update.message.voice:
                with tempfile.TemporaryDirectory() as tmp:
                    ogg = Path(tmp) / "puente.ogg"
                    await sintetizar(mensaje_para_adulto, ogg, voz=VOZ_TTS)
                    with open(ogg, "rb") as audio:
                        await adulto_bot.send_voice(chat_id=adulto_id, voice=audio)
            else:
                await adulto_bot.send_message(chat_id=adulto_id, text=mensaje_para_adulto)
        log.info(f"Mensaje de {nombre} entregado a {adulto_nombre}: '{texto[:60]}'")
        await update.message.reply_text(f"Listo, le mandé a {adulto_nombre}: \"{mensaje_para_adulto}\"")
    except Exception as e:
        log.error(f"Error enviando mensaje a {adulto_nombre}: {e}")
        await update.message.reply_text(f"Hubo un error al enviarle el mensaje a {adulto_nombre}.")

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not FAMILIAR_TOKEN:
        raise RuntimeError("Falta FAMILIAR_BOT_TOKEN en .env")

    app = Application.builder().token(FAMILIAR_TOKEN).build()

    conv_editar = ConversationHandler(
        entry_points=[CommandHandler("editar", cmd_editar)],
        states={
            ELIGIENDO:  [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_seccion)],
            RECIBIENDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_contenido)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    conv_mensaje = ConversationHandler(
        entry_points=[CommandHandler("mensaje", cmd_mensaje)],
        states={
            ESPERANDO_MENSAJE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_mensaje_familiar),
                MessageHandler(filters.VOICE, recibir_mensaje_familiar),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start",          cmd_start))
    app.add_handler(CommandHandler("ayuda",          cmd_ayuda))
    app.add_handler(CommandHandler("nombre",         cmd_nombre))
    app.add_handler(CommandHandler("perfil",         cmd_perfil))
    app.add_handler(CommandHandler("suscriptores",   cmd_suscriptores))
    app.add_handler(CommandHandler("stats",          cmd_stats))
    app.add_handler(CommandHandler("aprendizajes",   cmd_aprendizajes))
    app.add_handler(CommandHandler("vincular",       cmd_vincular))
    app.add_handler(CommandHandler("misadultos",     cmd_misadultos))
    app.add_handler(CommandHandler("elegir",         cmd_elegir))
    app.add_handler(conv_editar)
    app.add_handler(conv_mensaje)

    log.info("Bot familiar iniciando...")
    async with app:
        await app.initialize()
        try:
            await app.bot.set_my_commands(COMANDOS_TELEGRAM)
            log.info(f"Comandos publicados en Telegram: {len(COMANDOS_TELEGRAM)}")
        except Exception as e:
            log.warning(f"No pude publicar los comandos en Telegram: {e}")
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        hb_mod.iniciar_heartbeat("familiar")
        try:
            await asyncio.Event().wait()
        finally:
            await app.updater.stop()
            await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
