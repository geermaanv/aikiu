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
        configurar.main()

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
        configurar.main()
    perfil = (tmp_path / "perfil.md").read_text(encoding="utf-8")
    assert "completar con los familiares" in perfil.lower()
    assert "Sin notas cargadas" in perfil
