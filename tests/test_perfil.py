"""
Tests unitarios para las funciones de lectura/escritura del perfil
y gestión de suscriptores en familiar_bot.
"""

import json
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers que replican la lógica de familiar_bot sin importar el módulo
# completo (que arrastra dependencias de Telegram y .env)
# ---------------------------------------------------------------------------

import re

def leer_seccion(perfil: str, nombre: str) -> str:
    match = re.search(
        rf'## {re.escape(nombre)}\n(.*?)(?=\n## |\Z)',
        perfil, re.DOTALL
    )
    return match.group(1).strip() if match else "(sección no encontrada)"

def actualizar_seccion(perfil: str, nombre: str, nuevo: str) -> str:
    return re.sub(
        rf'(## {re.escape(nombre)}\n)(.*?)(?=\n## |\Z)',
        lambda m: f"{m.group(1)}{nuevo.strip()}\n\n",
        perfil, flags=re.DOTALL
    )


PERFIL_EJEMPLO = """\
# Perfil de Marta

## Quién es
- Tiene 83 años
- Vive sola en Buenos Aires

## Gustos y temas que la alegran
- La música de tango
- Las plantas del balcón

## Salud (para contexto, no para diagnosticar)
- Toma medicación para la presión
"""


# ---------------------------------------------------------------------------
# leer_seccion
# ---------------------------------------------------------------------------

def test_leer_seccion_existente():
    resultado = leer_seccion(PERFIL_EJEMPLO, "Quién es")
    assert "83 años" in resultado
    assert "Buenos Aires" in resultado

def test_leer_seccion_no_incluye_siguiente_seccion():
    resultado = leer_seccion(PERFIL_EJEMPLO, "Quién es")
    assert "tango" not in resultado

def test_leer_seccion_inexistente():
    resultado = leer_seccion(PERFIL_EJEMPLO, "Sección que no existe")
    assert resultado == "(sección no encontrada)"

def test_leer_ultima_seccion():
    resultado = leer_seccion(PERFIL_EJEMPLO, "Salud (para contexto, no para diagnosticar)")
    assert "presión" in resultado


# ---------------------------------------------------------------------------
# actualizar_seccion
# ---------------------------------------------------------------------------

def test_actualizar_seccion_cambia_contenido():
    nuevo = actualizar_seccion(PERFIL_EJEMPLO, "Quién es", "- Tiene 79 años\n- Vive en Palermo")
    assert "79 años" in nuevo
    assert "83 años" not in nuevo

def test_actualizar_seccion_no_toca_otras_secciones():
    nuevo = actualizar_seccion(PERFIL_EJEMPLO, "Quién es", "- Tiene 79 años")
    assert "tango" in nuevo
    assert "presión" in nuevo

def test_actualizar_seccion_preserva_titulo():
    nuevo = actualizar_seccion(PERFIL_EJEMPLO, "Quién es", "- Contenido nuevo")
    assert "## Quién es" in nuevo


# ---------------------------------------------------------------------------
# Familiares (formato unificado {chat_id, nombre})
# ---------------------------------------------------------------------------

def _cargar(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

def _guardar(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

def test_agregar_familiar_nuevo(tmp_path):
    path = tmp_path / "familiares.json"
    _guardar(path, [])
    familiares = _cargar(path)
    if not any(f["chat_id"] == 123456 for f in familiares):
        familiares.append({"chat_id": 123456, "nombre": ""})
        _guardar(path, familiares)
    result = _cargar(path)
    assert len(result) == 1
    assert result[0]["chat_id"] == 123456

def test_no_duplica_familiar(tmp_path):
    path = tmp_path / "familiares.json"
    _guardar(path, [{"chat_id": 123456, "nombre": "Germán"}])
    familiares = _cargar(path)
    if not any(f["chat_id"] == 123456 for f in familiares):
        familiares.append({"chat_id": 123456, "nombre": ""})
        _guardar(path, familiares)
    assert len(_cargar(path)) == 1

def test_nombre_registrado(tmp_path):
    path = tmp_path / "familiares.json"
    _guardar(path, [{"chat_id": 111, "nombre": "Germán"}, {"chat_id": 222, "nombre": "Lao"}])
    familiares = _cargar(path)
    nombres = {f["chat_id"]: f["nombre"] for f in familiares}
    assert nombres[111] == "Germán"
    assert nombres[222] == "Lao"

def test_actualizar_nombre_familiar(tmp_path):
    path = tmp_path / "familiares.json"
    _guardar(path, [{"chat_id": 111, "nombre": ""}])
    familiares = _cargar(path)
    for f in familiares:
        if f["chat_id"] == 111:
            f["nombre"] = "Germán"
    _guardar(path, familiares)
    assert _cargar(path)[0]["nombre"] == "Germán"

def test_suscriptores_son_lista_de_ids(tmp_path):
    path = tmp_path / "familiares.json"
    _guardar(path, [{"chat_id": 111, "nombre": "Germán"}, {"chat_id": 222, "nombre": "Lao"}])
    familiares = _cargar(path)
    ids = [f["chat_id"] for f in familiares]
    assert ids == [111, 222]

def test_archivo_inexistente_retorna_lista_vacia(tmp_path):
    path = tmp_path / "no_existe.json"
    assert _cargar(path) == []
