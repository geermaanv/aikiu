"""
Estado por familiar para soportar el many-to-many adulto ↔ familiar.

Un familiar puede estar vinculado a 0..N adultos. Cuando solo está vinculado
a uno, los comandos del bot familiar (perfil, stats, mensaje, etc.) operan
sobre ese hogar automáticamente. Cuando hay varios, hay que elegir cuál es
el "adulto activo" para los próximos comandos vía `/elegir <chat_id>`.

La membresía (qué familiares están vinculados a qué adulto) vive en cada
`instances/<adulto>/familiares.json` — esa es la fuente de verdad. Acá solo
guardamos:

- nombre que el familiar usa para identificarse (`Germán`, `Lao`, etc.)
- `adulto_activo`: cuál de sus adultos es el "default" cuando manda comandos.

Archivo: `_familiar_state.json` en el registry root.
Estructura:
    {
      "<chat_id_familiar>": {
        "nombre": "Germán",
        "adulto_activo": 42,
        "registered_at": "2026-..."
      },
      ...
    }
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from core import hogar as hogar_mod
from core.utils import load_json, write_json_atomic

log = logging.getLogger("aikiu.familiar")

FAMILIAR_STATE_FILENAME = "_familiar_state.json"


def _path() -> Path:
    return hogar_mod.instances_root() / FAMILIAR_STATE_FILENAME


def _leer_todos() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir(data: dict) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".famstate.", suffix=".json.tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Estado por familiar
# ---------------------------------------------------------------------------

def leer_estado(chat_id_familiar: int) -> dict:
    """Estado del familiar (nombre, adulto_activo, etc.). {} si no existe."""
    return _leer_todos().get(str(chat_id_familiar), {})


def asegurar_familiar(chat_id_familiar: int, *, nombre: Optional[str] = None) -> bool:
    """Da de alta al familiar si no estaba. True si era nuevo."""
    todos = _leer_todos()
    clave = str(chat_id_familiar)
    if clave in todos:
        # Si nos pasaron un nombre y antes no tenía, lo registramos.
        if nombre and not todos[clave].get("nombre"):
            todos[clave]["nombre"] = nombre
            _escribir(todos)
        return False
    todos[clave] = {
        "nombre": nombre or "",
        "adulto_activo": None,
        "registered_at": datetime.now().isoformat(timespec="seconds"),
    }
    _escribir(todos)
    log.info(f"familiar nuevo: chat_id={chat_id_familiar} nombre={nombre!r}")
    return True


def actualizar_nombre(chat_id_familiar: int, nombre: str) -> None:
    todos = _leer_todos()
    clave = str(chat_id_familiar)
    if clave not in todos:
        asegurar_familiar(chat_id_familiar, nombre=nombre)
        return
    todos[clave]["nombre"] = nombre
    _escribir(todos)


def nombre_de(chat_id_familiar: int, fallback: str = "Tu familiar") -> str:
    estado = leer_estado(chat_id_familiar)
    return estado.get("nombre") or fallback


# ---------------------------------------------------------------------------
# Vínculos familiar ↔ adultos
# ---------------------------------------------------------------------------

def adultos_de(chat_id_familiar: int) -> list[int]:
    """
    Devuelve los chat_ids de los adultos a los que este familiar está vinculado.

    Se deriva escaneando cada `instances/<adulto>/familiares.json` y buscando
    al familiar. Es una operación O(n_hogares) pero los volúmenes esperados
    son pequeños (1-10 adultos por familiar).
    """
    vinculados: list[int] = []
    for adulto_id in hogar_mod.listar_hogares():
        fams = load_json(hogar_mod.familiares_path(adulto_id), default=[])
        if any(int(f.get("chat_id", -1)) == int(chat_id_familiar) for f in fams):
            vinculados.append(adulto_id)
    return vinculados


def vincular(chat_id_familiar: int, chat_id_adulto: int, *, nombre: str = "") -> bool:
    """
    Asocia al familiar con el adulto, agregándolo a
    `instances/<adulto>/familiares.json`. Devuelve True si era un vínculo nuevo.

    Idempotente: si ya estaba vinculado, no duplica (pero actualiza el nombre
    si vino uno nuevo).
    """
    if not hogar_mod.existe_hogar(chat_id_adulto):
        return False
    path = hogar_mod.familiares_path(chat_id_adulto)
    fams = load_json(path, default=[])
    encontrado = False
    for f in fams:
        if int(f.get("chat_id", -1)) == int(chat_id_familiar):
            encontrado = True
            if nombre and not f.get("nombre"):
                f["nombre"] = nombre
            break
    if not encontrado:
        fams.append({"chat_id": int(chat_id_familiar), "nombre": nombre})
    write_json_atomic(path, fams)

    # Si era el primer (o único) adulto del familiar, lo dejamos como activo.
    estado = leer_estado(chat_id_familiar)
    if not estado.get("adulto_activo"):
        setear_adulto_activo(chat_id_familiar, chat_id_adulto)

    return not encontrado


def desvincular(chat_id_familiar: int, chat_id_adulto: int) -> bool:
    """Quita al familiar del `familiares.json` del adulto. True si quitó algo."""
    path = hogar_mod.familiares_path(chat_id_adulto)
    fams = load_json(path, default=[])
    nuevos = [f for f in fams if int(f.get("chat_id", -1)) != int(chat_id_familiar)]
    if len(nuevos) == len(fams):
        return False
    write_json_atomic(path, nuevos)

    # Si el familiar tenía a ese adulto como activo, lo cambiamos por otro
    # de su lista (o lo dejamos en None si no le quedan más).
    estado = leer_estado(chat_id_familiar)
    if estado.get("adulto_activo") == int(chat_id_adulto):
        otros = adultos_de(chat_id_familiar)
        setear_adulto_activo(chat_id_familiar, otros[0] if otros else None)
    return True


# ---------------------------------------------------------------------------
# Adulto activo
# ---------------------------------------------------------------------------

def adulto_activo(chat_id_familiar: int) -> Optional[int]:
    """
    Devuelve el adulto activo del familiar.

    - Si tiene el `adulto_activo` seteado y sigue vinculado, ese.
    - Si tiene un solo adulto vinculado, ese (auto).
    - Si tiene varios y no eligió, None.
    """
    vinculados = adultos_de(chat_id_familiar)
    if not vinculados:
        return None
    if len(vinculados) == 1:
        # Auto-pick: ningún ruido para el familiar con un solo adulto.
        return vinculados[0]
    estado = leer_estado(chat_id_familiar)
    activo = estado.get("adulto_activo")
    if isinstance(activo, int) and activo in vinculados:
        return activo
    return None  # ambiguo: tiene que elegir


def setear_adulto_activo(chat_id_familiar: int, chat_id_adulto: Optional[int]) -> None:
    todos = _leer_todos()
    clave = str(chat_id_familiar)
    if clave not in todos:
        todos[clave] = {
            "nombre": "",
            "adulto_activo": chat_id_adulto,
            "registered_at": datetime.now().isoformat(timespec="seconds"),
        }
    else:
        todos[clave]["adulto_activo"] = chat_id_adulto
    _escribir(todos)


def limpiar_hogar_borrado(chat_id_adulto: int) -> int:
    """
    Reasigna el `adulto_activo` de cualquier familiar que lo tuviera
    apuntando a `chat_id_adulto`. Pensado para llamar después de borrar
    un hogar — el `familiares.json` del hogar ya no existe, así que
    `adultos_de` no lo va a listar más, pero el activo persistido en
    `_familiar_state.json` queda apuntando al vacío.

    Para cada familiar afectado:
    - Si tiene otros adultos vinculados, lo cambia al primero disponible.
    - Si no le queda ninguno, lo deja en `None` (el familiar tendrá que
      vincularse de nuevo con un código).

    Devuelve la cantidad de familiares cuyo activo se modificó.
    """
    todos = _leer_todos()
    afectados = 0
    cambios = False
    for clave, datos in list(todos.items()):
        if not isinstance(datos, dict):
            continue
        if datos.get("adulto_activo") != int(chat_id_adulto):
            continue
        try:
            fam_id = int(clave)
        except ValueError:
            continue
        otros = adultos_de(fam_id)
        nuevo_activo = otros[0] if otros else None
        datos["adulto_activo"] = nuevo_activo
        afectados += 1
        cambios = True
        log.info(
            f"familiar_state: familiar {fam_id} → activo reasignado "
            f"{chat_id_adulto} → {nuevo_activo} (hogar borrado)"
        )
    if cambios:
        _escribir(todos)
    return afectados
