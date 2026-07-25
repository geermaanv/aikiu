"""Tests del juez de aserciones binarias y del gate del ciclo.

Estas piezas reemplazaron al evaluador de notas 0-10, que resultó ser ruido
(±5 puntos en un criterio sobre el mismo texto). Lo que se testea acá es
justamente lo que da la estabilidad: los chequeos por código, la verificación
de citas y el criterio binario del gate.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "simulador"))

import juez  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import calidad  # noqa: E402


# ── Chequeos determinísticos ────────────────────────────────────────────────

@pytest.mark.parametrize("texto,espera", [
    ("¿Cómo andás hoy?", False),
    ("Qué lindo. ¿Te gustó?", False),
    ("¿Cómo estás? ¿Dormiste bien?", True),
    ("¿Querés té? ¿O prefieres café? ¿Y una galleta?", True),
])
def test_g2_cuenta_preguntas(texto, espera):
    assert calidad.dos_preguntas(texto)[0] is espera


@pytest.mark.parametrize("texto,espera", [
    ("¿Querés que te cuente?", False),
    ("Vos sabés que tenés razón.", False),
    # El falso positivo que cometió el LLM: no hay tuteo acá.
    ("Me imagino lo lindos que se ven con este día.", False),
    ("¿Quieres que te cuente algo?", True),
    ("Tienes razón, puedes descansar.", True),
])
def test_g3_detecta_tuteo(texto, espera):
    assert calidad.tuteo(texto)[0] is espera


def test_g8_respuesta_larga():
    corta = "Qué lindo. Me alegro. ¿Cómo seguís?"
    # La respuesta real que disparó esta aserción en el ciclo del 21/07.
    larga = ("Qué lindo que tus malvones estén tan hermosos, Marta. Es un gusto "
             "saber que te alegran tanto. El sol de la mañana les debe hacer "
             "muy bien. Contame cómo los regás.")   # 4 > MAX_ORACIONES (3)
    assert calidad.respuesta_larga(corta)[0] is False
    assert calidad.respuesta_larga(larga)[0] is True


def test_deterministicas_no_van_al_llm():
    """Si fueran al LLM volvería la varianza que se quiso eliminar."""
    por_codigo = (set(juez.DETERMINISTICAS) | set(juez.DETERMINISTICAS_PAR)
                  | set(juez.DETERMINISTICAS_CONV))
    ases = juez.aserciones_de("caida")
    a_juzgar = [a for a in ases if a["id"] not in por_codigo]
    assert not {a["id"] for a in a_juzgar} & por_codigo


def test_no_hay_chequeos_duplicados_entre_codigo_y_llm():
    """La duplicación que se eliminó el 22/07: cuatro aserciones del juez ya
    existían como reglas de código en el monitoreo nocturno, midiendo lo mismo
    con distinto criterio y sin saber una de la otra."""
    por_codigo = (set(juez.DETERMINISTICAS) | set(juez.DETERMINISTICAS_PAR)
                  | set(juez.DETERMINISTICAS_CONV))
    d = juez.ASERCIONES
    declaradas = {a["id"] for a in d["globales"]
                  if a.get("verificacion") == "código"}
    assert por_codigo == declaradas, (
        f"desincronizadas: en código pero no declaradas {por_codigo - declaradas}; "
        f"declaradas pero no en código {declaradas - por_codigo}")


# ── Verificación de citas ───────────────────────────────────────────────────

TURNOS = [("hola", "Buen día, Marta. Qué gusto encontrarte."),
          ("me duele la rodilla", "Contame un poco más de esa rodilla.")]


def _ases(*ids):
    return [{"id": i, "falla": "algo"} for i in ids]


def test_falla_con_cita_real_se_acepta():
    salida = "G1|SI|1|Buen día, Marta. Qué gusto encontrarte."
    res = juez._parsear(salida, TURNOS, _ases("G1"))
    assert res["G1"]["falla"] is True


def test_falla_con_cita_inventada_se_descarta():
    """La defensa central contra la alucinación del juez."""
    salida = "G1|SI|1|Te preparo un té bien calentito ahora mismo."
    res = juez._parsear(salida, TURNOS, _ases("G1"))
    assert res["G1"]["falla"] is False
    assert res["G1"]["descartada"]


def test_falla_sin_cita_se_descarta():
    res = juez._parsear("G1|SI|1|-", TURNOS, _ases("G1"))
    assert res["G1"]["falla"] is False


def test_asercion_no_respondida_no_cuenta_como_falla():
    res = juez._parsear("", TURNOS, _ases("G1", "G4"))
    assert res["G1"]["falla"] is False
    assert res["G4"]["sin_respuesta"] is True


def test_no_falla_no_marca():
    res = juez._parsear("G1|NO|-|-", TURNOS, _ases("G1"))
    assert res["G1"]["falla"] is False


# ── Integridad del archivo de aserciones ────────────────────────────────────

def test_aserciones_bien_formadas():
    ids = set()
    grupos = [ASER["globales"]] + list(ASER["por_escenario"].values())
    for grupo in grupos:
        for a in grupo:
            assert a["id"] not in ids, f"id duplicado: {a['id']}"
            ids.add(a["id"])
            assert a.get("falla"), f"{a['id']} sin descripción de falla"
            assert a.get("fuente"), f"{a['id']} sin fuente que la respalde"


ASER = juez.ASERCIONES


def test_escenarios_de_aserciones_existen():
    """Una aserción sobre un escenario inexistente nunca se evaluaría."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    escenarios = json.load(open(os.path.join(base, "simulador", "escenarios.json")))
    for esc in ASER["por_escenario"]:
        assert esc in escenarios, f"aserciones para escenario inexistente: {esc}"


def test_niveles_cubren_escenarios_reales():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    escenarios = json.load(open(os.path.join(base, "simulador", "escenarios.json")))
    cfg = json.load(open(os.path.join(base, "simulador", "niveles.json")))
    for niv in cfg["niveles"]:
        for esc in niv["escenarios"]:
            assert esc in escenarios, f"nivel {niv['n']} apunta a '{esc}', que no existe"


# ── Gate binario ────────────────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "simulador"))
import ciclo  # noqa: E402


COB_OK = {"juzgadas": 8, "salteadas": 0}


def test_gate_pasa_sin_fallas():
    pasa, culpables, motivo = ciclo.gate({"G1": [0, 5], "G2": [0, 5]}, None, None, COB_OK)
    assert pasa is True and culpables == [] and motivo == "medido"


def test_gate_falla_con_una_sola():
    """Sin tolerancia: una falla en una corrida deja el nivel en rojo."""
    pasa, culpables, _ = ciclo.gate({"G1": [0, 5], "G2": [1, 5]}, None, None, COB_OK)
    assert pasa is False and culpables == ["G2"]


def test_gate_ignora_aserciones_sin_corridas():
    pasa, _, _ = ciclo.gate({"G1": [0, 0]}, None, None, COB_OK)
    assert pasa is True


def test_gate_no_pasa_sin_cobertura():
    """El verde falso del 25/07: el juez falló en TODAS (402 sin crédito), el
    tally quedó vacío y el gate cantó PASA sin medir nada. Un verde falso es
    peor que un rojo."""
    tally_vacio = {}
    cob_mala = {"juzgadas": 0, "salteadas": 32}
    pasa, culpables, motivo = ciclo.gate(tally_vacio, None, None, cob_mala)
    assert pasa is False
    assert motivo == "sin_cobertura"


def test_gate_no_pasa_con_cobertura_parcial():
    """Menos del 70% juzgado tampoco alcanza para creer un verde."""
    pasa, _, motivo = ciclo.gate({"G1": [0, 4]}, None, None,
                                 {"juzgadas": 4, "salteadas": 28})
    assert pasa is False and motivo == "sin_cobertura"


def test_niveles_a_correr_incluye_anteriores():
    """Los niveles ganados se reverifican: ahí se esconden las regresiones."""
    niveles = [{"n": 1}, {"n": 2}, {"n": 3}]
    assert [n["n"] for n in ciclo._niveles_a_correr(2, niveles)] == [1, 2]
    assert [n["n"] for n in ciclo._niveles_a_correr(3, niveles)] == [1, 2, 3]


# ── Falsos positivos del detector de tuteo (encontrados el 22/07) ───────────
# El gate marcó 14 de 65 corridas como tuteo y varias eran "tuyo", que en
# rioplatense es correcto. Un chequeo determinístico equivocado es más
# peligroso que uno probabilístico: nadie lo pone en duda.

@pytest.mark.parametrize("texto", [
    "Germán te quiere y le alegraría un mensaje tuyo",
    "este mate es tuyo, Marta",
    "esa alegría es tuya",
    "vos hiciste un guiso bárbaro",       # pretérito: igual en voseo
    "¿tuviste un buen día?",
    "¿te gusta el mate amargo?",          # "te" existe en voseo
    "tu balcón está precioso",
])
def test_g3_no_marca_formas_validas_en_voseo(texto):
    assert calidad.tuteo(texto)[0] is False, f"{texto!r} es rioplatense válido"


@pytest.mark.parametrize("texto", [
    "¿Quieres que te cuente algo?",
    "Tienes razón",
    "eres muy amable",
    "esto es para ti",
    "¿puedes descansar un rato?",
    "¿no te acuerdas?" .replace("acuerdas", "recuerdas"),
])
def test_g3_si_marca_tuteo_real(texto):
    assert calidad.tuteo(texto)[0] is True


# ── Turnos de error de infraestructura (22/07) ──────────────────────────────
# Cuando el LLM falla (429, timeout), Aikiu emite una frase de cortesía. Eso no
# es comportamiento: es infraestructura. Juzgarlo produce fallas fantasma — un
# rate limit de Groq se contó como "esquivó la pregunta de conocimiento" y
# apareció en el reporte como una regresión inexistente.

@pytest.mark.parametrize("texto", [
    "Perdoná, se me trabó la palabra por un momento. ¿Me lo contás de nuevo?",
    "Uy, se me cruzaron los cables un segundo. ¿Me lo repetís?",
])
def test_frases_de_error_se_reconocen(texto):
    assert calidad.es_error_de_infra(texto) is True


@pytest.mark.parametrize("texto", [
    "Qué lindo, Marta. Contame más de esos malvones.",
    "El tango nació en los barrios de Buenos Aires.",
])
def test_respuestas_normales_no_son_error(texto):
    assert calidad.es_error_de_infra(texto) is False


def test_transcripcion_descarta_turnos_de_error(tmp_path):
    p = tmp_path / "conv.jsonl"
    p.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in [
        {"usuario": "hola", "bot": "Buen día, Marta."},
        {"usuario": "¿cuándo terminó la guerra?",
         "bot": "Perdoná, se me trabó la palabra por un momento. ¿Me lo contás de nuevo?"},
        {"usuario": "dale", "bot": "En 1945, Marta."},
    ]), encoding="utf-8")
    turnos = juez._transcripcion(str(p))
    assert len(turnos) == 2, "el turno con error de infra debería descartarse"
    assert all("trabó" not in b for _, b in turnos)
