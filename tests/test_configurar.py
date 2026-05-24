"""Tests para configurar.py — asistente interactivo de configuración."""

import builtins
from pathlib import Path
from unittest.mock import patch

import pytest

import configurar


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def test_titulo_imprime(capsys):
    configurar.titulo("Sección 1")
    out = capsys.readouterr().out
    assert "Sección 1" in out
    assert "─" in out


def test_items_md_lista_simple():
    assert configurar.items_md(["uno", "dos"]) == "- uno\n- dos"


def test_items_md_vacio():
    assert configurar.items_md([]) == ""


# ---------------------------------------------------------------------------
# preguntar
# ---------------------------------------------------------------------------

def test_preguntar_con_default_usa_default_si_enter():
    with patch.object(builtins, "input", return_value=""):
        assert configurar.preguntar("¿X?", default="Marta") == "Marta"


def test_preguntar_con_default_usa_input_si_hay():
    with patch.object(builtins, "input", return_value="Sofía"):
        assert configurar.preguntar("¿X?", default="Marta") == "Sofía"


def test_preguntar_sin_default_con_input():
    with patch.object(builtins, "input", return_value="hola"):
        assert configurar.preguntar("¿X?") == "hola"


def test_preguntar_strip():
    with patch.object(builtins, "input", return_value="  hola  "):
        assert configurar.preguntar("?") == "hola"


# ---------------------------------------------------------------------------
# preguntar_lista
# ---------------------------------------------------------------------------

def test_preguntar_lista_usa_defaults_por_default():
    defaults = ["a", "b", "c"]
    with patch.object(builtins, "input", return_value=""):
        assert configurar.preguntar_lista("¿X?", defaults) == defaults


def test_preguntar_lista_usa_defaults_si_s():
    defaults = ["a", "b"]
    with patch.object(builtins, "input", return_value="s"):
        assert configurar.preguntar_lista("X", defaults) == defaults


def test_preguntar_lista_acepta_custom_si_n():
    defaults = ["x"]
    inputs = iter(["n", "uno", "dos", ""])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        res = configurar.preguntar_lista("X", defaults)
    assert res == ["uno", "dos"]


def test_preguntar_lista_n_pero_sin_items_cae_a_defaults():
    defaults = ["x"]
    inputs = iter(["n", ""])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        res = configurar.preguntar_lista("X", defaults)
    assert res == defaults


# ---------------------------------------------------------------------------
# preguntar_lista_libre
# ---------------------------------------------------------------------------

def test_preguntar_lista_libre_acepta_items():
    inputs = iter(["uno", "dos", ""])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        res = configurar.preguntar_lista_libre("X")
    assert res == ["uno", "dos"]


def test_preguntar_lista_libre_vacia():
    with patch.object(builtins, "input", return_value=""):
        assert configurar.preguntar_lista_libre("X") == []


# ---------------------------------------------------------------------------
# main — flujo completo
# ---------------------------------------------------------------------------

def test_main_genera_perfil_y_actualiza_config(tmp_path, monkeypatch):
    # config.yml de ejemplo en tmp
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        'nombre_adulto_mayor: "Marta"\n'
        'nombre_asistente: "Clara"\n'
        'perfil: "perfil.md"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(configurar, "BASE_DIR", tmp_path)

    # Inputs del flujo (en orden):
    # 1) nombre, edad, ciudad, descripcion, asistente
    # 2) familiares: tres líneas + vacío
    # 3) ¿Usar defaults gustos? s
    # 4) ¿Usar defaults salud? (preguntar_lista_libre) - dos líneas + vacío
    # 5) ¿Usar defaults temas? s
    # 6) ¿Usar defaults reglas? s
    inputs = iter([
        "Sofía",       # nombre
        "85",           # edad
        "Mendoza",      # ciudad
        "Alegre",       # descripcion
        "Aurora",       # nombre asistente
        # familiares (lista_libre)
        "Hija Ana",
        "Hijo Juan",
        "",  # cierre
        # gustos
        "s",
        # salud (lista_libre)
        "Toma para la presión",
        "",
        # temas (lista con defaults)
        "s",
        # reglas (lista con defaults)
        "s",
    ])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        configurar.main(["--template"])

    perfil_path = tmp_path / "perfil.md"
    assert perfil_path.exists()
    perfil = perfil_path.read_text(encoding="utf-8")
    assert "Sofía" in perfil
    assert "85 años" in perfil
    assert "Mendoza" in perfil
    assert "Aurora" in perfil
    assert "Hija Ana" in perfil
    assert "Hijo Juan" in perfil
    assert "Toma para la presión" in perfil
    # Y el config se actualizó
    cfg_text = config_path.read_text(encoding="utf-8")
    assert "Sofía" in cfg_text
    assert "Aurora" in cfg_text


def test_main_sin_familiares_pone_placeholder(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        'nombre_adulto_mayor: "Marta"\nnombre_asistente: "Clara"\nperfil: "perfil.md"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(configurar, "BASE_DIR", tmp_path)
    inputs = iter([
        "Sofía", "85", "Mendoza", "Alegre", "Aurora",  # identidad
        "",   # familiares vacíos
        "s",  # gustos defaults
        "",   # salud vacía
        "s",  # temas defaults
        "s",  # reglas defaults
    ])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        configurar.main(["--template"])
    perfil = (tmp_path / "perfil.md").read_text(encoding="utf-8")
    assert "completar con los familiares" in perfil.lower()
    assert "Sin notas cargadas" in perfil


# ---------------------------------------------------------------------------
# generar_perfil — función pura usada por wizards del bot
# ---------------------------------------------------------------------------

def test_generar_perfil_con_nombre_arma_seccion_quien_es():
    datos = {
        "nombre": "Pedro",
        "edad": "78",
        "ciudad": "Rosario",
        "descripcion": "Tranquilo, le gusta el dominó",
        "nombre_asistente": "Sofi",
        "familiares": ["Hijo Lucas, vive cerca"],
        "gustos": ["Dominó", "Mate amargo"],
        "salud": ["Toma para el colesterol"],
    }
    perfil = configurar.generar_perfil(datos)
    assert "# Perfil de Pedro" in perfil
    assert "Pedro, 78 años, vive en Rosario" in perfil
    assert "Tranquilo, le gusta el dominó" in perfil
    assert "Al asistente lo conoce como Sofi" in perfil
    assert "Hijo Lucas" in perfil
    assert "## Aprendizajes" in perfil
    assert "## Ajustes sugeridos" in perfil


def test_generar_perfil_sin_nombre_devuelve_esqueleto_neutro():
    perfil = configurar.generar_perfil({})
    assert "# Perfil del adulto" in perfil
    assert "Nombre y edad pendientes" in perfil
    # No debe contener nombres propios filtrados
    assert "Marta" not in perfil
    assert "Pedro" not in perfil


def test_generar_perfil_solo_nombre_no_explota():
    perfil = configurar.generar_perfil({"nombre": "Ana"})
    assert "# Perfil de Ana" in perfil
    assert "- Ana" in perfil
    # No imprime "X años" si no hay edad
    assert "años" not in perfil
    # Asistente por defecto: Clara
    assert "Al asistente lo conoce como Clara" in perfil


def test_generar_perfil_sin_edad_pero_con_ciudad():
    perfil = configurar.generar_perfil({"nombre": "Luis", "ciudad": "Tigre"})
    assert "Luis, vive en Tigre" in perfil


# ---------------------------------------------------------------------------
# Modo --chat-id: configura un hogar existente
# ---------------------------------------------------------------------------

def test_main_chat_id_inexistente_sale_con_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path / "instances"))
    with pytest.raises(SystemExit) as exc:
        configurar.main(["--chat-id", "9999"])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "no existe" in err
    assert "/start" in err


def test_main_chat_id_existente_reescribe_perfil_y_state(tmp_path, monkeypatch):
    monkeypatch.setenv("AIKIU_REGISTRY", str(tmp_path / "instances"))
    # Crear hogar simulado
    from core import hogar as hogar_mod
    hogar_mod.crear_hogar(12345, nombre="Pre-existente")

    inputs = iter([
        "Pedro", "78", "Rosario", "Tranquilo", "Sofi",  # identidad
        "Hijo Lucas", "",                                # familiares
        "s",                                              # gustos defaults
        "Presión arterial", "",                          # salud
        "s",                                              # temas defaults
        "s",                                              # reglas defaults
    ])
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        configurar.main(["--chat-id", "12345"])

    perfil = hogar_mod.perfil_path(12345).read_text(encoding="utf-8")
    assert "# Perfil de Pedro" in perfil
    assert "Hijo Lucas" in perfil

    import json
    state = json.loads(hogar_mod.state_path(12345).read_text(encoding="utf-8"))
    assert state["nombre_adulto_mayor"] == "Pedro"
    assert state["nombre_asistente"] == "Sofi"
    assert state["ciudad"] == "Rosario"
    assert state["perfil_completo"] is True
    # owner_chat_id preservado del crear_hogar
    assert state["owner_chat_id"] == 12345


def test_main_template_sin_nombre_genera_esqueleto(tmp_path, monkeypatch):
    """--template con Enter en todas las preguntas genera el esqueleto neutro."""
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        'nombre_adulto_mayor: ""\nnombre_asistente: "Clara"\nperfil: "perfil.md"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(configurar, "BASE_DIR", tmp_path)
    # Todas las preguntas con Enter (default neutro) → 13 Enters
    inputs = iter([""] * 30)
    with patch.object(builtins, "input", side_effect=lambda *_: next(inputs)):
        configurar.main(["--template"])
    perfil = (tmp_path / "perfil.md").read_text(encoding="utf-8")
    assert "# Perfil del adulto" in perfil
    assert "Nombre y edad pendientes" in perfil
    assert "Marta" not in perfil
