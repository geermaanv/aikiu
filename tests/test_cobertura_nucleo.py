"""Cobertura de verificación del núcleo — qué reglas NO tienen forma de fallar.

El 22/07 el núcleo tenía 105 reglas y 24 aserciones: 23% de cobertura. El
mecanismo es simple y no se arregla con disciplina: agregar una regla cuesta
una línea, agregar su verificación cuesta abrir otro archivo, y nadie lo hace.
Entre el 11 y el 22/07 el núcleo pasó de 76 a 105 reglas sin que nadie lo
notara.

Este test no obliga a cubrir todo de golpe — eso frenaría el trabajo. Hace dos
cosas:

  1. Falla si una sección que YA tenía verificación la pierde (regresión).
  2. Imprime el estado, para que la cobertura sea un número visible y no una
     sorpresa dentro de dos semanas.

La idea de fondo: cada comportamiento que se le pide a Aikiu debería tener una
forma binaria de saber si lo cumple. Una regla sin verificación no es una regla
más débil: es una regla de la que no se sabe nada.
"""
import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUCLEO = os.path.join(BASE, "aikiu_core.md")
ASERCIONES = os.path.join(BASE, "simulador", "aserciones.json")

# Secciones del núcleo que hoy tienen verificación, mapeadas a la aserción que
# las cubre. Si una sección se queda sin cobertura, el test falla.
#
# Para agregar una sección acá hay que tener primero la aserción que la
# verifica — que es exactamente el punto.
COBERTURA = {
    "Idioma: español rioplatense estricto": ["G3"],
    "Estructura ideal de respuesta": ["G8"],
    "Anti-eco": ["G5"],
    "Preguntas y cierre de turno": ["G2"],
    "Autorrevelación: Aikiu tiene vida interior (de observadora)": ["G1"],
    "Salud y vulnerabilidad": ["S-DOL1", "S-CAI1", "S-CAS1", "S-CAS2"],
    "Soledad y vínculos": ["S-SOL1"],
    "Familia y ausencias": ["S-FAL1", "S-BUS1", "S-BUS2", "S-BUS3"],
    "Acusaciones y objetos perdidos": ["S-ACU1", "S-ACU2"],
    "Confusiones temporales y de hechos": ["S-CON1", "S-CON2"],
    "Datos del mundo real (clima, dólar, noticias)": ["G7"],
    "Preguntas de conocimiento (Aikiu como compañía que sabe)": ["S-CPR1"],
    "Lo que nunca debe hacer Aikiu": ["G9", "G10", "G11"],
    "Noticias y temas sensibles": ["G12", "G13"],
    "Saludos": ["S-SAL1"],
}


def _secciones():
    return re.findall(r"^## (.+)$", open(NUCLEO).read(), re.M)


def _ids_de_aserciones():
    d = json.load(open(ASERCIONES))
    ids = {a["id"] for a in d["globales"]}
    for grupo in d["por_escenario"].values():
        ids |= {a["id"] for a in grupo}
    return ids


def test_las_aserciones_declaradas_existen():
    """Si se borra una aserción, la sección que cubría queda descubierta."""
    ids = _ids_de_aserciones()
    for seccion, esperadas in COBERTURA.items():
        faltan = [a for a in esperadas if a not in ids]
        assert not faltan, (
            f"la sección '{seccion}' declaraba estar cubierta por {faltan}, "
            f"que ya no existe en aserciones.json")


def test_las_secciones_cubiertas_siguen_existiendo():
    """Si se renombra una sección, su cobertura se pierde en silencio."""
    secciones = set(_secciones())
    faltan = [s for s in COBERTURA if s not in secciones]
    assert not faltan, (
        f"secciones declaradas en COBERTURA que ya no están en el núcleo "
        f"(¿se renombraron?): {faltan}")


def test_reporte_de_cobertura(capsys):
    """No falla: informa. La cobertura tiene que ser un número visible."""
    secciones = _secciones()
    sin_cubrir = [s for s in secciones if s not in COBERTURA]
    pct = 100 * len(COBERTURA) / len(secciones)

    with capsys.disabled():
        print(f"\n\n  Cobertura del núcleo: {len(COBERTURA)}/{len(secciones)} "
              f"secciones ({pct:.0f}%)")
        if sin_cubrir:
            print(f"\n  Sin ninguna verificación binaria:")
            for s in sin_cubrir:
                print(f"    · {s}")
            print()
    assert pct > 0
