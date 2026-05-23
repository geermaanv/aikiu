"""
Estado interno de Andromarta — ánimo, energía, salud y eventos del día.

Se persiste en `andromarta/data/estado.json` (ignorado por git) y evoluciona:
- Cada día nuevo se regenera (con sesgo a la continuidad: si ayer estaba
  cansada hay más chances de que hoy también).
- Durante el día el ánimo oscila levemente con la hora.
- Eventos (visita, llamado, ir al médico) se rifan con baja probabilidad.

El módulo es deliberadamente determinístico-con-ruido: usa random pero las
probabilidades están a la vista para que sea fácil ajustarlas.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime
from pathlib import Path

from core.utils import load_json

DATA_DIR = Path(__file__).parent / "data"
ESTADO_PATH = DATA_DIR / "estado.json"

SINTOMAS_POSIBLES = [
    "rodillas",
    "no dormí bien",
    "dolor de cabeza suave",
    "cansancio",
    "molestia en la espalda",
]

EVENTOS_POSIBLES = [
    "llamó mi hijo Roberto",
    "vino la vecina del 4° a tomar mate",
    "fui al kiosco a la mañana",
    "tengo que ir al médico la semana que viene",
    "limpié el balcón",
    "no salí en todo el día",
    "se cortó la luz una hora",
    "vi una película vieja en la tele",
]


def _nuevo_dia(estado_ayer: dict | None) -> dict:
    """Genera el estado del día, sesgado por el de ayer si existe."""
    base_animo = 6
    base_energia = 6
    if estado_ayer:
        # Continuidad: el estado de hoy se acerca al de ayer ± 2
        base_animo = estado_ayer.get("animo", 6)
        base_energia = estado_ayer.get("energia", 6)

    animo = max(2, min(10, base_animo + random.randint(-2, 2)))
    energia = max(2, min(10, base_energia + random.randint(-2, 2)))

    sintomas = []
    if random.random() < 0.4:  # 40% de los días aparece algo
        sintomas.append(random.choice(SINTOMAS_POSIBLES))
    if random.random() < 0.1:  # 10% dos cosas a la vez
        otro = random.choice(SINTOMAS_POSIBLES)
        if otro not in sintomas:
            sintomas.append(otro)

    eventos = []
    n_eventos = random.choices([0, 1, 2], weights=[2, 5, 3])[0]
    for _ in range(n_eventos):
        ev = random.choice(EVENTOS_POSIBLES)
        if ev not in eventos:
            eventos.append(ev)

    return {
        "fecha": date.today().isoformat(),
        "animo": animo,
        "energia": energia,
        "sintomas": sintomas,
        "eventos": eventos,
        "ultima_actualizacion": datetime.now().isoformat(timespec="seconds"),
        "iniciativa_disparada": False,
    }


def cargar_estado() -> dict:
    """Devuelve el estado de hoy. Si es de un día anterior, regenera."""
    estado = load_json(ESTADO_PATH, default={})
    hoy = date.today().isoformat()
    if estado.get("fecha") != hoy:
        nuevo = _nuevo_dia(estado_ayer=estado if estado else None)
        guardar_estado(nuevo)
        return nuevo
    return estado


def guardar_estado(estado: dict) -> None:
    estado["ultima_actualizacion"] = datetime.now().isoformat(timespec="seconds")
    ESTADO_PATH.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def descripcion_humana(estado: dict) -> str:
    """Convierte el estado en un párrafo legible para meter en el system prompt."""
    animo = estado.get("animo", 6)
    energia = estado.get("energia", 6)
    sintomas = estado.get("sintomas", [])
    eventos = estado.get("eventos", [])

    if animo >= 8:
        nivel = "Hoy estás de buen humor, conversadora."
    elif animo >= 5:
        nivel = "Hoy tu ánimo está tranquilo, ni feliz ni triste."
    else:
        nivel = "Hoy estás melancólica, con poca chispa."

    if energia <= 4:
        nivel += " Andás con poca energía y un poco lenta."

    partes = [nivel]
    if sintomas:
        partes.append(f"Síntoma(s) de hoy: {', '.join(sintomas)}.")
    if eventos:
        partes.append(f"Evento(s) del día: {', '.join(eventos)}.")
    return " ".join(partes)


def hora_del_dia() -> str:
    """Etiqueta de franja horaria para decidir tono y probabilidad de iniciativa."""
    h = datetime.now().hour
    if 6 <= h < 11:
        return "mañana"
    if 11 <= h < 14:
        return "mediodía"
    if 14 <= h < 18:
        return "tarde"
    if 18 <= h < 22:
        return "noche"
    return "madrugada"


def probabilidad_iniciativa() -> float:
    """Probabilidad de que Andromarta arranque ella la conversación, según hora."""
    franja = hora_del_dia()
    return {
        "mañana":    0.35,
        "mediodía":  0.15,
        "tarde":     0.25,
        "noche":     0.20,
        "madrugada": 0.02,  # casi nunca; insomnio ocasional
    }.get(franja, 0.10)
