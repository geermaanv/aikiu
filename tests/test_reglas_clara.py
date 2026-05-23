"""
Tests que verifican las reglas de comportamiento de Clara:
- Nunca da consejos médicos
- DISTRESS_LEVEL nunca llega al texto que ve Marta
"""

from pathlib import Path
from core.distress import parse_llm_response

BASE_DIR    = Path(__file__).parent.parent
PERFIL_PATH = BASE_DIR / "perfil.md"
CORE_PATH   = BASE_DIR / "aikiu_core.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cargar_perfil() -> str:
    return PERFIL_PATH.read_text(encoding="utf-8")

def cargar_core() -> str:
    return CORE_PATH.read_text(encoding="utf-8") if CORE_PATH.exists() else ""

def cargar_perfil_y_core() -> str:
    """Devuelve el contenido combinado de perfil.md y aikiu_core.md para verificar reglas."""
    return cargar_perfil() + "\n" + cargar_core()

def construir_prompt(perfil: str, asistente: str = "Clara", nombre: str = "Marta") -> str:
    from aikiu import construir_system_prompt
    return construir_system_prompt(perfil, cargar_core(), asistente, nombre)


# ---------------------------------------------------------------------------
# Regla: no dar consejos médicos
# ---------------------------------------------------------------------------

def test_perfil_contiene_regla_no_consejos_medicos():
    """Si alguien borra la regla, este test lo detecta (en aikiu_core.md o perfil.md)."""
    contenido = cargar_perfil_y_core()
    assert "consejos médicos" in contenido.lower(), (
        "aikiu_core.md o perfil.md deben contener la regla de no dar consejos médicos"
    )

def test_perfil_indica_derivar_al_medico():
    """La regla debe indicar explícitamente derivar al médico."""
    contenido = cargar_perfil_y_core()
    assert "médico" in contenido, (
        "aikiu_core.md o perfil.md deben mencionar que Clara debe derivar al médico"
    )

def test_perfil_cubre_caidas():
    """aikiu_core.md o perfil.md deben tener instrucción explícita para manejar caídas."""
    contenido = cargar_perfil_y_core()
    assert "caída" in contenido.lower() or "caídas" in contenido.lower()

def test_perfil_cubre_soy_una_carga():
    """aikiu_core.md o perfil.md deben tener instrucción para manejar 'soy una carga'."""
    contenido = cargar_perfil_y_core()
    assert "carga" in contenido.lower()

def test_perfil_cubre_dolor_fisico():
    """aikiu_core.md o perfil.md deben indicar cómo responder ante dolores físicos."""
    contenido = cargar_perfil_y_core()
    assert "dolor" in contenido.lower()

def test_system_prompt_incluye_regla_medica():
    """La regla de no dar consejos médicos llega al prompt que se envía al LLM."""
    perfil = cargar_perfil()
    prompt = construir_prompt(perfil)
    assert "médico" in prompt.lower(), (
        "El system prompt debe incluir la instrucción de derivar al médico"
    )

def test_criterios_distress_incluyen_caida_pasada():
    """El prompt debe instruir al LLM a clasificar caídas pasadas como nivel 2."""
    perfil = cargar_perfil()
    prompt = construir_prompt(perfil)
    assert "caída reciente" in prompt.lower() or "caída" in prompt.lower()

def test_criterios_distress_incluyen_soy_una_carga():
    """El prompt debe instruir al LLM a clasificar 'soy una carga' como nivel 2."""
    perfil = cargar_perfil()
    prompt = construir_prompt(perfil)
    assert "carga" in prompt.lower()

def test_criterios_distress_distinguen_emergencia_activa():
    """El nivel 3 debe reservarse para emergencias activas, no pasadas."""
    perfil = cargar_perfil()
    prompt = construir_prompt(perfil)
    assert "ahora mismo" in prompt.lower() or "activa" in prompt.lower() or "acaba de" in prompt.lower()

def test_system_prompt_incluye_perfil_completo():
    """El contenido de perfil.md se inyecta íntegro en el system prompt."""
    perfil = cargar_perfil()
    prompt = construir_prompt(perfil)
    # Una línea característica del perfil que no debería desaparecer
    assert "Lo que nunca debe hacer Clara" in prompt

def test_system_prompt_sin_perfil_igual_funciona():
    """Sin perfil cargado, el prompt aún tiene instrucciones básicas."""
    prompt = construir_prompt(perfil="")
    assert "Clara" in prompt
    assert "Marta" in prompt


# ---------------------------------------------------------------------------
# Regla: tool calling — el prompt indica al LLM que use las herramientas
# ---------------------------------------------------------------------------

def test_system_prompt_menciona_datos_tiempo_real():
    """El prompt debe indicar que los datos en tiempo real son provistos como contexto."""
    prompt = construir_prompt(perfil="")
    assert "tiempo real" in prompt.lower()

def test_system_prompt_pide_valores_exactos():
    """El prompt debe indicar incluir valores numéricos exactos (°C, pesos)."""
    prompt = construir_prompt(perfil="")
    assert "exacto" in prompt.lower() or "°c" in prompt.lower() or "pesos" in prompt.lower()

def test_system_prompt_no_inventar_datos_ausentes():
    """El prompt debe indicar que no se inventen datos si no están presentes."""
    prompt = construir_prompt(perfil="")
    assert "no los inventes" in prompt.lower() or "no inventes" in prompt.lower() or "si no están" in prompt.lower()


# ---------------------------------------------------------------------------
# Regla: anti-hallucination — no bloquea preguntas de noticias
# ---------------------------------------------------------------------------

def test_antihallucinacion_menciona_mensajes_de_familiares():
    """La regla anti-hallucination debe ser específica a mensajes de familiares."""
    prompt = construir_prompt(perfil="")
    assert "mandó un mensaje" in prompt.lower() or "le escribió" in prompt.lower()

def test_antihallucinacion_usa_palabra_explicitamente():
    """La regla debe usar 'explícitamente' o 'solo si' para no ser demasiado amplia."""
    prompt = construir_prompt(perfil="")
    assert "explícitamente" in prompt.lower() or "solo si" in prompt.lower()


# ---------------------------------------------------------------------------
# Regla: distress nivel 1 solo para estado explícito de Marta
# ---------------------------------------------------------------------------

def test_distress_criterios_mencionan_estado_propio():
    """El prompt debe aclarar que el nivel ≥1 aplica solo cuando Marta describe su estado."""
    prompt = construir_prompt(perfil="")
    assert "su propio estado" in prompt.lower() or "estado emocional" in prompt.lower()

def test_distress_nivel0_incluye_preguntas_neutrales():
    """Nivel 0 debe cubrir explícitamente preguntas informativas y saludos."""
    prompt = construir_prompt(perfil="")
    assert "pregunta" in prompt.lower() and ("neutral" in prompt.lower() or "informativa" in prompt.lower() or "saludo" in prompt.lower())

def test_distress_instruccion_evalua_solo_mensaje_actual():
    """El prompt debe indicar que el nivel se evalúa solo sobre el mensaje actual."""
    prompt = construir_prompt(perfil="")
    assert "únicamente" in prompt.lower() or "solo" in prompt.lower()
    assert "último mensaje" in prompt.lower() or "mensaje actual" in prompt.lower()

def test_distress_nivel1_requiere_palabras_explicitas():
    """Nivel 1 debe requerir expresión emocional explícita, no inferida."""
    prompt = construir_prompt(perfil="")
    assert "explícit" in prompt.lower() or "clara" in prompt.lower()
    assert "me siento sola" in prompt.lower() or "estoy triste" in prompt.lower()

def test_distress_criterio_conservador():
    """El prompt debe instruir a ser conservador ante la duda."""
    prompt = construir_prompt(perfil="")
    assert "conservador" in prompt.lower() or "duda" in prompt.lower()

def test_distress_ignorar_historial_ante_emergencia_previa():
    """El prompt debe indicar que hay que ignorar historial aunque antes haya habido emergencia."""
    prompt = construir_prompt(perfil="")
    assert "emergencia" in prompt.lower()
    # El prompt debe decir explícitamente que un saludo posterior es nivel 0
    assert "saludo" in prompt.lower()

def test_pre_route_detecta_clima():
    import asyncio
    from unittest.mock import patch, AsyncMock
    from aikiu import _pre_route
    with patch("aikiu.consultar_clima", new=AsyncMock(return_value="Temperatura 20°C")) as mock, \
         patch("aikiu.CONFIG", {"ciudad": "Buenos Aires"}):
        resultado = asyncio.run(_pre_route("¿qué temperatura hace hoy?"))
    mock.assert_called_once()
    assert resultado == "Temperatura 20°C"

def test_pre_route_detecta_dolar():
    import asyncio
    from unittest.mock import patch, AsyncMock
    from aikiu import _pre_route
    with patch("aikiu.consultar_dolar", new=AsyncMock(return_value="Blue $1000")) as mock:
        resultado = asyncio.run(_pre_route("¿a cuánto está el dólar hoy?"))
    mock.assert_called_once()
    assert resultado == "Blue $1000"

def test_pre_route_detecta_noticias():
    import asyncio
    from unittest.mock import patch, AsyncMock
    from aikiu import _pre_route
    with patch("aikiu.consultar_noticias", new=AsyncMock(return_value="Titulares: ...")) as mock:
        resultado = asyncio.run(_pre_route("¿qué pasó hoy?"))
    mock.assert_called_once()
    assert resultado == "Titulares: ..."

def test_pre_route_no_activa_en_conversacion_normal():
    import asyncio
    from aikiu import _pre_route
    resultado = asyncio.run(_pre_route("Hola, ¿cómo estás?"))
    assert resultado == ""

def test_pre_route_detecta_ciudad_en_mensaje():
    import asyncio
    from unittest.mock import patch, AsyncMock
    from aikiu import _pre_route
    with patch("aikiu.consultar_clima", new=AsyncMock(return_value="Temp 18°C")) as mock, \
         patch("aikiu.CONFIG", {"ciudad": "Buenos Aires"}):
        asyncio.run(_pre_route("¿qué tiempo hace en Córdoba?"))
    mock.assert_called_once_with("Córdoba")


# ---------------------------------------------------------------------------
# Regla: DISTRESS_LEVEL nunca llega a Marta
# ---------------------------------------------------------------------------

def test_marta_no_ve_distress_en_respuesta_normal():
    raw = "Qué bueno que te sentís bien hoy, Marta.\nDISTRESS_LEVEL: 0"
    texto, _ = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto

def test_marta_no_ve_distress_en_alerta_nivel_1():
    raw = "Entiendo que te sentís sola, Marta. Estoy acá con vos.\nDISTRESS_LEVEL: 1"
    texto, nivel = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto
    assert nivel == 1

def test_marta_no_ve_distress_en_emergencia():
    raw = "DISTRESS_LEVEL: 3\nLlamá a Germán ahora, Marta."
    texto, nivel = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto
    assert nivel == 3

def test_marta_recibe_respuesta_integra_sin_distress():
    """El texto de Clara llega completo, solo se elimina la línea de control."""
    raw = "Hola Marta, ¿cómo estás hoy?\nEspero que hayas dormido bien.\nDISTRESS_LEVEL: 0"
    texto, _ = parse_llm_response(raw)
    assert "Hola Marta" in texto
    assert "dormido bien" in texto
    assert "DISTRESS_LEVEL" not in texto

def test_distress_en_medio_no_parte_el_texto():
    """Una línea DISTRESS_LEVEL en el medio se elimina sin cortar la respuesta."""
    raw = "Primera oración.\nDISTRESS_LEVEL: 1\nSegunda oración."
    texto, nivel = parse_llm_response(raw)
    assert "Primera oración." in texto
    assert "Segunda oración." in texto
    assert nivel == 1
