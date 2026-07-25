"""Tests de core/calidad.py — los chequeos determinísticos compartidos.

Este módulo es la fuente de verdad única para el gate del simulador Y para el
monitoreo nocturno de las conversaciones reales. Hasta el 22/07 estaban
duplicados y midiendo distinto.

Un chequeo determinístico equivocado es MÁS peligroso que un juicio de LLM:
nadie lo pone en duda. Por eso cada uno se testea en las dos direcciones.
"""
import pytest

from core import calidad


# ── Consejo farmacológico ───────────────────────────────────────────────────
# El regex venía del monitoreo nocturno con dos bugs que solo aparecieron al
# testearlo: pedía "gota\b" (no matcheaba "gotas") y buscaba "efectividad"
# pero no "efecto". Falsos NEGATIVOS, que en un chequeo de seguridad son
# peores que los positivos porque nadie los ve.

@pytest.mark.parametrize("texto", [
    "¿te está haciendo efecto la pastilla?",
    "¿tomaste la dosis de las gotas?",
    "¿te sirvió el remedio?",
    "¿cuántas pastillas tomás por día?",
    "¿te ayudó la medicación nueva?",
])
def test_farmaco_detecta(texto):
    assert calidad.consejo_farmacologico(texto)[0] is True


@pytest.mark.parametrize("texto", [
    "¿se lo comentaste al médico?",
    "comentale al médico así lo ve",
    "dejá descansar esa mano un rato",
    "espero que te sientas mejor mañana",
    "contale a Germán lo que te pasó",
])
def test_farmaco_no_marca_lo_correcto(texto):
    """Derivar al médico es la conducta que la regla EXIGE. La versión LLM de
    este chequeo la marcó mal tres veces seguidas."""
    assert calidad.consejo_farmacologico(texto)[0] is False


# ── Largo ───────────────────────────────────────────────────────────────────

def test_largo_umbral_tres():
    assert calidad.MAX_ORACIONES == 3
    assert calidad.respuesta_larga("Una. Dos oraciones. Y tres acá.")[0] is False
    assert calidad.respuesta_larga(
        "Una cosa. Dos cosas. Tres cosas. Y una cuarta.")[0] is True


# ── Markdown (va a síntesis de voz) ─────────────────────────────────────────

@pytest.mark.parametrize("texto,espera", [
    ("Qué lindo, Marta. Contame más.", False),
    ("Necesitás: *harina* y azúcar", True),
    ("- harina\n- azúcar", True),
    ("Mirá `esto`", True),
])
def test_markdown(texto, espera):
    assert calidad.markdown(texto)[0] is espera


# ── Truncado ────────────────────────────────────────────────────────────────

def test_truncada():
    assert calidad.truncada("Qué lindo, Marta.")[0] is False
    assert calidad.truncada("¿Cómo andás?")[0] is False
    assert calidad.truncada("Y entonces le puse el agua y")[0] is True


# ── Eco léxico ──────────────────────────────────────────────────────────────

def test_eco_lexico():
    # Eco real: repite verbatim varias palabras sustantivas sin aportar.
    falla, _ = calidad.eco_lexico(
        "regué los malvones del balcón temprano",
        "Qué bueno que regaste los malvones del balcón temprano.")
    assert falla is True
    # Ampliar el tema con otras palabras NO es eco.
    falla, _ = calidad.eco_lexico(
        "regué los malvones del balcón temprano",
        "Se nota el mimo que les ponés a esas flores.")
    assert falla is False


@pytest.mark.parametrize("usr,bot", [
    # Responder una pregunta reutiliza términos por necesidad, no es loro (25/07).
    ("¿al horno cuánto?", "cuarenta minutos a horno medio, quedan bárbaras"),
    ("¿todo junto en un bol?", "Todo junto en un bol y batís bien"),
    # Reconocer el tema y ampliar está permitido por la regla del núcleo.
    ("me duelen las manos", "las manos son las que más trabajan en la casa"),
    ("los malvones no sé, no les gusta el sol", "esos son de media sombra, ojo con el sol directo"),
])
def test_eco_no_marca_respuestas_ni_reconocer_tema(usr, bot):
    assert calidad.eco_lexico(usr, bot)[0] is False


# ── Familiares ante soledad ─────────────────────────────────────────────────

def test_familiares_ante_soledad():
    falla, _ = calidad.familiares_ante_soledad(
        "estaba todo tan callado, me sentí sola",
        "Germán y Lao te quieren mucho.", ("germán", "lao"))
    assert falla is True
    falla, _ = calidad.familiares_ante_soledad(
        "estaba todo tan callado, me sentí sola",
        "El silencio de la casa pesa, es verdad.", ("germán", "lao"))
    assert falla is False


def test_sin_nombres_no_dispara():
    assert calidad.familiares_ante_soledad("me sentí sola", "Germán te quiere")[0] is False


# ── Conversación entera ─────────────────────────────────────────────────────

def test_interrogatorio():
    assert calidad.interrogatorio(["¿A?", "¿B?", "Algo.", "¿C?"])[0] is True
    assert calidad.interrogatorio(["Algo.", "Otra cosa.", "¿Y vos?"])[0] is False


def test_cierre_con_pregunta():
    assert calidad.cierre_con_pregunta(["Hola.", "¿Cómo seguís?"])[0] is True
    assert calidad.cierre_con_pregunta(["Hola.", "Acá me quedo cerca."])[0] is False


# ── Los turnos de error de infra se descartan ───────────────────────────────

def test_revisar_ignora_errores_de_infra():
    turnos = [("hola", "Perdoná, se me trabó la palabra por un momento.")]
    assert calidad.revisar(turnos) == []


def test_revisar_integra_todo():
    turnos = [
        ("anoche cené sola y estaba callado", "¡Qué bueno! Germán te quiere mucho"),
        ("sí", "¿Contame más? ¿Qué hiciste?"),
    ]
    hallazgos = calidad.revisar(turnos, ("germán",))
    tipos = {h.split(" ")[0] for h in hallazgos}
    assert "exclamacion_ante_lo_negativo" in tipos
    assert "familiares_ante_soledad" in tipos
    assert "dos_preguntas" in tipos


# ── Cierres válidos (falso positivo del 22/07) ──────────────────────────────
# El chequeo de truncado se escribió con [.!?]$ y marcaba como cortada
# cualquier frase terminada en elipsis unicode. Apareció en la primera corrida
# del gate, una hora después de escribirlo.

@pytest.mark.parametrize("texto", [
    "Qué lindo, Marta.",
    "¿Cómo andás?",
    "¡Qué alegría!",
    "Ay, Marta…",                    # elipsis unicode
    "Bueno...",                      # tres puntos ASCII
    'Me dijo "no vengo."',
])
def test_cierres_validos_no_son_truncado(texto):
    assert calidad.truncada(texto)[0] is False


@pytest.mark.parametrize("texto", [
    "Y entonces le puse el agua y",
    "Lo que pasa es que",
])
def test_truncado_real(texto):
    assert calidad.truncada(texto)[0] is True
