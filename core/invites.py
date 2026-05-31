"""
Códigos de invitación para vincular familiares con adultos (hogares).

Flujo:
1. El adulto manda `/invitar` al bot principal → se genera un código corto
   (6 chars alfanuméricos sin ambigüedad) y se persiste en `_invites.json`.
2. El adulto le da el código al familiar (verbal, WhatsApp, lo que sea).
3. El familiar manda `/vincular <CODIGO>` al bot familiar → se consume el
   código y queda asociado a ese adulto en `instances/<adulto>/familiares.json`.

Los códigos son single-use y expiran en 24 horas por default.
"""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core import hogar as hogar_mod

log = logging.getLogger("aikiu.invites")

# Lock para serializar `consumir()` dentro del mismo proceso. Sin esto,
# dos /vincular concurrentes podrían leer el mismo `usos_restantes` y
# ambos descontar (consumir el código dos veces). Como el bot familiar
# corre en un solo proceso/event loop, este lock alcanza para protegerlo.
#
# Entre procesos distintos (aikiu.py escribe `_invites.json` cuando se
# generan códigos, familiar_bot.py lo lee/escribe cuando se consumen)
# no hay race posible porque sólo familiar_bot.py llama a `consumir`.
_consumir_lock = threading.Lock()

# Alfabeto sin ambigüedad: sin 0/O/1/I/l (suelen confundirse al dictar).
ALFABETO_CODIGO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LONGITUD_CODIGO = 6
TTL_DEFAULT_HORAS = 24
USOS_DEFAULT = 1

INVITES_FILENAME = "_invites.json"


def _path_invites() -> Path:
    """Vive en el registry root para que sea global a todos los hogares."""
    return hogar_mod.instances_root() / INVITES_FILENAME


def _leer() -> dict[str, dict]:
    path = _path_invites()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _escribir_atomico(data: dict) -> None:
    path = _path_invites()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".invites.", suffix=".json.tmp", dir=str(path.parent))
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


def _generar_codigo_aleatorio(rng: random.Random) -> str:
    return "".join(rng.choices(ALFABETO_CODIGO, k=LONGITUD_CODIGO))


def generar_codigo(
    adulto_chat_id: int,
    *,
    ttl_horas: int = TTL_DEFAULT_HORAS,
    usos: int = USOS_DEFAULT,
    rng: Optional[random.Random] = None,
) -> str:
    """
    Crea un código de invitación nuevo y lo persiste.

    Devuelve el código generado. Si por casualidad colisiona con uno
    existente (improbable: 32^6 = 1GB de espacio), intenta hasta 5 veces.
    """
    rng = rng or random.SystemRandom()
    invites = _leer()
    purgar_expirados(invites)

    for _ in range(5):
        codigo = _generar_codigo_aleatorio(rng)
        if codigo not in invites:
            break
    else:
        raise RuntimeError("No pude generar un código único después de 5 intentos")

    ahora = datetime.now()
    invites[codigo] = {
        "adulto_chat_id": int(adulto_chat_id),
        "creado_en": ahora.isoformat(timespec="seconds"),
        "expira_en": (ahora + timedelta(hours=ttl_horas)).isoformat(timespec="seconds"),
        "usos_restantes": int(usos),
    }
    _escribir_atomico(invites)
    log.info(
        f"invite: código {codigo} creado para adulto {adulto_chat_id} "
        f"(ttl={ttl_horas}h, usos={usos})"
    )
    return codigo


def _expirado(entrada: dict, ahora: Optional[datetime] = None) -> bool:
    ahora = ahora or datetime.now()
    try:
        return datetime.fromisoformat(entrada["expira_en"]) <= ahora
    except (KeyError, ValueError, TypeError):
        return True


def purgar_expirados(invites: Optional[dict] = None) -> int:
    """Elimina los códigos vencidos. Devuelve cuántos se borraron.

    Si `invites` se pasa, opera in-place y NO escribe a disco (lo dejamos
    al caller). Si no se pasa, lee, purga y reescribe.
    """
    inplace = invites is not None
    if invites is None:
        invites = _leer()
    ahora = datetime.now()
    expirados = [c for c, e in invites.items() if _expirado(e, ahora)]
    for c in expirados:
        invites.pop(c, None)
    if expirados and not inplace:
        _escribir_atomico(invites)
    if expirados:
        log.info(f"invite: purgados {len(expirados)} código(s) expirado(s)")
    return len(expirados)


def consumir(codigo: str) -> Optional[int]:
    """
    Consume un código y devuelve el `adulto_chat_id` al que corresponde.

    - Devuelve None si el código no existe, está expirado, ya agotó usos
      o apunta a un hogar que ya no existe (p.ej. borrado por el admin).
    - Si tiene usos > 1, descuenta y deja el código vivo.
    - Si era el último uso, lo elimina.
    - El read-modify-write está protegido por un lock global del módulo
      para que dos /vincular simultáneos no puedan consumir el mismo
      código de un solo uso.

    El código se normaliza a mayúsculas para tolerar typing errors comunes.
    """
    if not codigo:
        return None
    codigo = codigo.strip().upper()

    with _consumir_lock:
        invites = _leer()
        purgar_expirados(invites)
        entrada = invites.get(codigo)
        if entrada is None:
            return None
        if _expirado(entrada):
            invites.pop(codigo, None)
            _escribir_atomico(invites)
            return None
        usos = int(entrada.get("usos_restantes", 0))
        if usos <= 0:
            invites.pop(codigo, None)
            _escribir_atomico(invites)
            return None

        adulto = int(entrada["adulto_chat_id"])

        # Si el hogar se borró después de que se generó el código, el código
        # queda huérfano. NO lo consumimos (lo dejamos como estaba para que
        # `purgar_de_hogar` o el TTL natural lo limpie) y devolvemos None
        # para que el bot familiar le explique al usuario que pida uno nuevo.
        if not hogar_mod.existe_hogar(adulto):
            log.warning(
                f"invite: código {codigo} apunta a hogar inexistente {adulto} "
                f"— no se consume, se elimina"
            )
            invites.pop(codigo, None)
            _escribir_atomico(invites)
            return None

        if usos <= 1:
            invites.pop(codigo, None)
        else:
            entrada["usos_restantes"] = usos - 1
        _escribir_atomico(invites)
        log.info(f"invite: código {codigo} consumido → adulto {adulto}")
        return adulto


def purgar_de_hogar(adulto_chat_id: int) -> int:
    """
    Elimina todos los códigos de invitación generados por `adulto_chat_id`.

    Se usa cuando el admin borra un hogar: deja `_invites.json` consistente
    para que ningún familiar pueda intentar vincular con un código apuntando
    a un hogar inexistente. Devuelve la cantidad borrada.
    """
    with _consumir_lock:
        invites = _leer()
        a_borrar = [
            codigo
            for codigo, entrada in invites.items()
            if int(entrada.get("adulto_chat_id", -1)) == int(adulto_chat_id)
        ]
        if not a_borrar:
            return 0
        for codigo in a_borrar:
            invites.pop(codigo, None)
        _escribir_atomico(invites)
        log.info(
            f"invite: purgados {len(a_borrar)} código(s) del hogar {adulto_chat_id}"
        )
        return len(a_borrar)


def inspeccionar(codigo: str) -> Optional[dict]:
    """Devuelve los metadatos del código sin consumirlo. Útil para previews."""
    if not codigo:
        return None
    return _leer().get(codigo.strip().upper())


def listar_de_adulto(adulto_chat_id: int) -> list[tuple[str, dict]]:
    """Códigos vivos generados para `adulto_chat_id`, ordenados por creación."""
    invites = _leer()
    purgar_expirados(invites)
    items = [
        (codigo, entrada)
        for codigo, entrada in invites.items()
        if entrada.get("adulto_chat_id") == int(adulto_chat_id)
    ]
    items.sort(key=lambda kv: kv[1].get("creado_en", ""), reverse=True)
    return items
