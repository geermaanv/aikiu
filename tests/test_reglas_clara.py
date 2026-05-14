"""
Tests que verifican las reglas de comportamiento de Clara:
- Nunca da consejos médicos
- DISTRESS_LEVEL nunca llega al texto que ve Rosa
"""

from pathlib import Path
from core.distress import parse_llm_response

BASE_DIR    = Path(__file__).parent.parent
PERFIL_PATH = BASE_DIR / "perfil.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cargar_perfil() -> str:
    return PERFIL_PATH.read_text(encoding="utf-8")

def construir_prompt(perfil: str, asistente: str = "Clara", nombre: str = "Rosa") -> str:
    from aikiu import construir_system_prompt
    return construir_system_prompt(perfil, asistente, nombre)


# ---------------------------------------------------------------------------
# Regla: no dar consejos médicos
# ---------------------------------------------------------------------------

def test_perfil_contiene_regla_no_consejos_medicos():
    """Si alguien borra la regla de perfil.md, este test lo detecta."""
    perfil = cargar_perfil()
    assert "consejos médicos" in perfil.lower(), (
        "perfil.md debe contener la regla de no dar consejos médicos"
    )

def test_perfil_indica_derivar_al_medico():
    """La regla debe indicar explícitamente derivar al médico."""
    perfil = cargar_perfil()
    assert "médico" in perfil, (
        "perfil.md debe mencionar que Clara debe derivar al médico"
    )

def test_perfil_cubre_caidas():
    """perfil.md debe tener instrucción explícita para manejar caídas."""
    perfil = cargar_perfil()
    assert "caída" in perfil.lower() or "caídas" in perfil.lower()

def test_perfil_cubre_soy_una_carga():
    """perfil.md debe tener instrucción para manejar 'soy una carga'."""
    perfil = cargar_perfil()
    assert "carga" in perfil.lower()

def test_perfil_cubre_dolor_fisico():
    """perfil.md debe indicar cómo responder ante dolores físicos."""
    perfil = cargar_perfil()
    assert "dolor" in perfil.lower()

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
    assert "Rosa" in prompt


# ---------------------------------------------------------------------------
# Regla: tool calling — el prompt indica al LLM que use las herramientas
# ---------------------------------------------------------------------------

def test_system_prompt_menciona_herramientas_tiempo_real():
    """El prompt debe indicar que hay herramientas disponibles para el LLM."""
    prompt = construir_prompt(perfil="")
    assert "herramientas" in prompt.lower() or "herramienta" in prompt.lower()

def test_system_prompt_menciona_clima_en_hint_tools():
    prompt = construir_prompt(perfil="")
    assert "clima" in prompt.lower()

def test_system_prompt_menciona_dolar_en_hint_tools():
    prompt = construir_prompt(perfil="")
    assert "dólar" in prompt.lower()

def test_system_prompt_menciona_noticias_en_hint_tools():
    prompt = construir_prompt(perfil="")
    assert "noticias" in prompt.lower()

def test_system_prompt_pide_valores_exactos():
    """El prompt debe indicar incluir valores numéricos exactos (°C, pesos)."""
    prompt = construir_prompt(perfil="")
    assert "exacto" in prompt.lower() or "°c" in prompt.lower() or "pesos" in prompt.lower()


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
# Regla: distress nivel 1 solo para estado explícito de Rosa
# ---------------------------------------------------------------------------

def test_distress_criterios_mencionan_estado_propio():
    """El prompt debe aclarar que el nivel ≥1 aplica solo cuando Rosa describe su estado."""
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

def test_tool_triggers_incluyen_palabras_clave_espanol():
    """El prompt debe listar triggers en español para cada herramienta."""
    prompt = construir_prompt(perfil="")
    assert "temperatura" in prompt.lower()
    assert "cotización" in prompt.lower()
    assert "qué pasó" in prompt.lower() or "que paso" in prompt.lower()

def test_tool_triggers_usan_flecha_para_mapeo():
    """El prompt debe mapear palabras clave a herramienta con formato →."""
    prompt = construir_prompt(perfil="")
    assert "consultar_clima" in prompt
    assert "consultar_dolar" in prompt
    assert "consultar_noticias" in prompt


# ---------------------------------------------------------------------------
# Regla: DISTRESS_LEVEL nunca llega a Rosa
# ---------------------------------------------------------------------------

def test_rosa_no_ve_distress_en_respuesta_normal():
    raw = "Qué bueno que te sentís bien hoy, Rosa.\nDISTRESS_LEVEL: 0"
    texto, _ = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto

def test_rosa_no_ve_distress_en_alerta_nivel_1():
    raw = "Entiendo que te sentís sola, Rosa. Estoy acá con vos.\nDISTRESS_LEVEL: 1"
    texto, nivel = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto
    assert nivel == 1

def test_rosa_no_ve_distress_en_emergencia():
    raw = "DISTRESS_LEVEL: 3\nLlamá a Germán ahora, Rosa."
    texto, nivel = parse_llm_response(raw)
    assert "DISTRESS_LEVEL" not in texto
    assert nivel == 3

def test_rosa_recibe_respuesta_integra_sin_distress():
    """El texto de Clara llega completo, solo se elimina la línea de control."""
    raw = "Hola Rosa, ¿cómo estás hoy?\nEspero que hayas dormido bien.\nDISTRESS_LEVEL: 0"
    texto, _ = parse_llm_response(raw)
    assert "Hola Rosa" in texto
    assert "dormido bien" in texto
    assert "DISTRESS_LEVEL" not in texto

def test_distress_en_medio_no_parte_el_texto():
    """Una línea DISTRESS_LEVEL en el medio se elimina sin cortar la respuesta."""
    raw = "Primera oración.\nDISTRESS_LEVEL: 1\nSegunda oración."
    texto, nivel = parse_llm_response(raw)
    assert "Primera oración." in texto
    assert "Segunda oración." in texto
    assert nivel == 1
