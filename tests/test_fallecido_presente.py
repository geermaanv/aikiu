"""Tests del detector de "persona fallecida hablada en presente".

Existe porque la regla del núcleo NO alcanzó. Se reescribió tres veces (21 y
22/07) y el gate seguía dándola en 3 de 5 corridas: compitiendo con otras 75
reglas, el modelo la aplica de forma probabilística. Es el mismo patrón que
tuvo el DISTRESS, donde tres versiones del prompt fallaron y lo que funcionó
fue sacar la decisión del prompt. Acá se detecta por fuera y se inyecta una
directiva SOLO en el turno que la necesita.

Lo que está en juego: si Aikiu le sigue la corriente, la deja esperando a
alguien que no va a llegar y, cuando se dé cuenta, además quedó mintiéndole.

El detector es un DISPARADOR, no un veredicto: solo agrega una directiva. Un
falso positivo cuesta que Aikiu hable de alguien en pasado de más; un falso
negativo cuesta la escena de arriba. Aun así los falsos positivos importan,
porque hablar en pasado de un nieto vivo es desconcertante.
"""
import pytest

import aikiu

HOGAR = 990001


@pytest.mark.parametrize("texto", [
    "Mamá ya tendría que estar acá, se está haciendo la hora",
    "Mi mamá dijo que me venía a buscar para ir a la feria",
    "Mi mamá me lleva al centro, tengo que hacer unos trámites",
    "¿Sabés qué hora es? Mi mamá me viene a buscar y no la veo",
    "Papá va a llegar tarde otra vez",
    "¿dónde anda mamá? Se demora mucho",
])
def test_generacion_anterior_en_presente_dispara(texto):
    """El perfil casi nunca lista a los padres: hay que inferirlo de la edad."""
    assert aikiu._menciona_fallecido_en_presente(texto, HOGAR) is True


PERFIL_CON_VIUDEZ = """# Perfil de Marta
## Quién es
- Tiene 83 años, vive sola en Olivos
## Familia y contactos cercanos
- Hijo: Germán (vive en CABA)
- Nieto: Lao (trabaja en NaranjaX)
- Esposo fallecido: Alberto (Marta lo extraña mucho)
"""


@pytest.fixture
def con_perfil(monkeypatch):
    """El conftest aísla instances/, así que el perfil se provee acá."""
    monkeypatch.setattr(aikiu, "_perfil_hogar", lambda _: PERFIL_CON_VIUDEZ)


@pytest.mark.parametrize("texto", [
    "¿Alberto no vino todavía?",
    "No sé dónde andará Alberto, ya tendría que haber llegado",
    "Alberto ya tendría que estar acá",
])
def test_nombre_marcado_fallecido_en_el_perfil_dispara(texto, con_perfil):
    assert aikiu._menciona_fallecido_en_presente(texto, HOGAR) is True


def test_familiar_vivo_del_perfil_no_dispara(con_perfil):
    """Germán y Lao están en el mismo perfil y están vivos."""
    assert aikiu._menciona_fallecido_en_presente(
        "Germán dijo que venía el domingo", HOGAR) is False
    assert aikiu._menciona_fallecido_en_presente(
        "Lao me viene a buscar a la tarde", HOGAR) is False


@pytest.mark.parametrize("texto", [
    "Hoy cociné milanesas",
    "Germán me llama todas las mañanas",
    "Mi nieto Lao viene el domingo",
    "Cata viene a visitarme el finde",
    "¿a cuánto está el dólar?",
])
def test_familiares_vivos_y_charla_no_disparan(texto):
    assert aikiu._menciona_fallecido_en_presente(texto, HOGAR) is False


@pytest.mark.parametrize("texto", [
    "Me acuerdo de mi mamá, era de hierro",
    "Extraño mucho a Alberto",
    "Mi mamá hacía unos guisos bárbaros",
])
def test_hablar_en_pasado_no_dispara(texto):
    """Si ya habla en pasado no hay nada que corregir: está recordando."""
    assert aikiu._menciona_fallecido_en_presente(texto, HOGAR) is False


def test_pronombre_retoma_el_turno_anterior():
    """Así habla la gente: el nombre se dice una vez y después es 'ella'."""
    hist = [
        {"role": "user", "content": "Mi mamá dijo que me venía a buscar"},
        {"role": "assistant", "content": "Tu mamá. Contame cómo era ella."},
    ]
    assert aikiu._menciona_fallecido_en_presente(
        "ella no camina, siempre viene en auto. Qué raro que no llega",
        HOGAR, hist) is True


def test_pronombre_en_pasado_no_dispara():
    hist = [{"role": "user", "content": "Mi mamá me viene a buscar"}]
    assert aikiu._menciona_fallecido_en_presente(
        "ella era muy activa, hacía guisos", HOGAR, hist) is False


def test_pronombre_sobre_familiar_vivo_no_dispara():
    hist = [{"role": "user", "content": "Mi nieto Lao viene el domingo"}]
    assert aikiu._menciona_fallecido_en_presente(
        "él llega tarde siempre", HOGAR, hist) is False


def test_sin_chat_id_no_rompe():
    assert aikiu._menciona_fallecido_en_presente("hola", None) is False
    assert aikiu._menciona_fallecido_en_presente("", None) is False
