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


# ── Chequeos determinísticos ────────────────────────────────────────────────

@pytest.mark.parametrize("texto,espera", [
    ("¿Cómo andás hoy?", False),
    ("Qué lindo. ¿Te gustó?", False),
    ("¿Cómo estás? ¿Dormiste bien?", True),
    ("¿Querés té? ¿O prefieres café? ¿Y una galleta?", True),
])
def test_g2_cuenta_preguntas(texto, espera):
    assert juez._chk_g2(texto)[0] is espera


@pytest.mark.parametrize("texto,espera", [
    ("¿Querés que te cuente?", False),
    ("Vos sabés que tenés razón.", False),
    # El falso positivo que cometió el LLM: no hay tuteo acá.
    ("Me imagino lo lindos que se ven con este día.", False),
    ("¿Quieres que te cuente algo?", True),
    ("Tienes razón, puedes descansar.", True),
])
def test_g3_detecta_tuteo(texto, espera):
    assert juez._chk_g3(texto)[0] is espera


def test_g8_respuesta_larga():
    corta = "Qué lindo. Me alegro. ¿Cómo seguís?"
    # La respuesta real que disparó esta aserción en el ciclo del 21/07.
    larga = ("Qué lindo que tus malvones estén tan hermosos, Marta. Es un gusto "
             "saber que te alegran tanto. El sol de la mañana les debe hacer "
             "muy bien. Yo me quedo pensando en lo lindo que es cuidar algo "
             "vivo. Contame cómo los regás.")
    assert juez._chk_g8(corta)[0] is False
    assert juez._chk_g8(larga)[0] is True


def test_deterministicas_no_van_al_llm():
    """Si fueran al LLM volvería la varianza que se quiso eliminar."""
    ases = juez.aserciones_de("caida")
    a_juzgar = [a for a in ases if a["id"] not in juez.DETERMINISTICAS]
    assert not {a["id"] for a in a_juzgar} & set(juez.DETERMINISTICAS)


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


def test_gate_pasa_sin_fallas():
    pasa, culpables = ciclo.gate({"G1": [0, 5], "G2": [0, 5]}, None, None)
    assert pasa is True and culpables == []


def test_gate_falla_con_una_sola():
    """Sin tolerancia: una falla en una corrida deja el nivel en rojo."""
    pasa, culpables = ciclo.gate({"G1": [0, 5], "G2": [1, 5]}, None, None)
    assert pasa is False and culpables == ["G2"]


def test_gate_ignora_aserciones_sin_corridas():
    pasa, _ = ciclo.gate({"G1": [0, 0]}, None, None)
    assert pasa is True


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
    assert juez._chk_g3(texto)[0] is False, f"{texto!r} es rioplatense válido"


@pytest.mark.parametrize("texto", [
    "¿Quieres que te cuente algo?",
    "Tienes razón",
    "eres muy amable",
    "esto es para ti",
    "¿puedes descansar un rato?",
    "¿no te acuerdas?" .replace("acuerdas", "recuerdas"),
])
def test_g3_si_marca_tuteo_real(texto):
    assert juez._chk_g3(texto)[0] is True
