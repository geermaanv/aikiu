"""
Asistente de configuración de Aikiu.

Tiene dos modos:

- `python configurar.py --template` (o sin flags): regenera el TEMPLATE
  neutro en `perfil.md` + `config.yml` de la raíz del repo. El template
  es lo que ven los hogares NUEVOS antes de que el adulto haga su
  onboarding por el bot — debe ser neutro, no debe contener datos de
  ningún adulto real.

- `python configurar.py --chat-id <id>`: configura un hogar EXISTENTE
  reescribiendo `instances/<id>/perfil.md` y agregando overrides en
  `instances/<id>/state.json`. Útil para configurar a Marta o a
  cualquier otro adulto desde la consola sin tocar el template.

La función `generar_perfil(datos) -> str` se reutiliza desde el wizard
del bot principal (`aikiu.py`) y desde `/configurar` del bot familiar
(`familiar_bot.py`).
"""

import argparse
import json
import re
import sys
import yaml
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# I/O interactivo (CLI)
# ---------------------------------------------------------------------------

def titulo(texto):
    print(f"\n{'─' * 52}")
    print(f"  {texto}")
    print(f"{'─' * 52}")


def preguntar(etiqueta, default=""):
    sufijo = f"  [Enter = {default!r}]: " if default else "  → "
    valor = input(f"\n  {etiqueta}\n{sufijo}").strip()
    return valor or default


def preguntar_lista(etiqueta, defaults):
    print(f"\n  {etiqueta}")
    print(f"  Predeterminados:")
    for item in defaults:
        print(f"    · {item}")
    usar = input("\n  ¿Usar estos? [S/n]: ").strip().lower()
    if usar != "n":
        return list(defaults)
    print("  Ingresá uno por línea. Enter vacío para terminar.")
    items = []
    while True:
        item = input("  · ").strip()
        if not item:
            break
        items.append(item)
    return items or list(defaults)


def preguntar_lista_libre(etiqueta):
    print(f"\n  {etiqueta}")
    print("  Ingresá uno por línea. Enter vacío para terminar.")
    items = []
    while True:
        item = input("  · ").strip()
        if not item:
            break
        items.append(item)
    return items


def items_md(lista):
    return "\n".join(f"- {i}" for i in lista)


# ---------------------------------------------------------------------------
# Generación del perfil — pura, reusable desde wizards del bot
# ---------------------------------------------------------------------------

# Defaults para el modo template (neutros, sin nombre propio).
DEFAULTS_TEMPLATE = {
    "nombre": "",
    "edad": "",
    "ciudad": "",
    "descripcion": "",
    "nombre_asistente": "Aikiu",
    "familiares": [],
    "gustos": [],
    "salud": [],
    "temas_sensibles": [
        "Guerras y conflictos: responder con calma y cambiar de tema",
        "Política: no opinar, redirigir a cómo está",
        "Catástrofes o muertes de famosos: calmar y redirigir",
        "Si suena triste o angustiada: contenerla con calidez y preguntar si necesita algo",
    ],
    "reglas_asistente": [
        "Oraciones muy cortas, simples y cálidas",
        "Español rioplatense natural, como un familiar cercano",
        "Nunca usar markdown ni símbolos — solo texto para escuchar",
        "Máximo 3 oraciones por respuesta",
        "Si no entiende algo, repetirlo de otra forma sin frustrarse",
        "Nunca dar detalles alarmantes sobre noticias del mundo",
    ],
}


def _esqueleto_template() -> str:
    """Esqueleto neutro que se usa cuando un hogar todavía no se onboardeó."""
    return (
        "# Perfil del adulto\n"
        "\n"
        "## Quién es\n"
        "- (Nombre y edad pendientes — se completan en el primer /start)\n"
        "\n"
        "## Familia y contactos cercanos\n"
        "- (Pendiente)\n"
        "\n"
        "## Gustos y temas que la alegran\n"
        "- (Pendiente)\n"
        "\n"
        "## Salud (para contexto, no para diagnosticar)\n"
        "- (Pendiente)\n"
        "\n"
        "## Temas a manejar con cuidado\n"
        f"{items_md(DEFAULTS_TEMPLATE['temas_sensibles'])}\n"
        "\n"
        "## Reglas del asistente\n"
        f"{items_md(DEFAULTS_TEMPLATE['reglas_asistente'])}\n"
        "\n"
        "## Aprendizajes\n"
        "\n"
        "## Ajustes sugeridos\n"
    )


def generar_perfil(datos: dict) -> str:
    """
    Genera el contenido completo de un `perfil.md` a partir de un dict
    con las respuestas del wizard. Las claves esperadas:

        nombre, edad, ciudad, descripcion, nombre_asistente,
        familiares (list), gustos (list), salud (list),
        temas_sensibles (list, opcional), reglas_asistente (list, opcional)

    Si `nombre` está vacío, genera el esqueleto neutro (sin datos
    personales). Si está poblado, arma el perfil completo.
    """
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        return _esqueleto_template()

    edad = (datos.get("edad") or "").strip()
    ciudad = (datos.get("ciudad") or "").strip()
    descripcion = (datos.get("descripcion") or "").strip()
    nombre_asistente = (datos.get("nombre_asistente") or "Aikiu").strip()
    familiares = datos.get("familiares") or ["(completar con los familiares cercanos)"]
    gustos = datos.get("gustos") or ["(completar con sus gustos)"]
    salud = datos.get("salud") or ["Sin notas cargadas"]
    temas = datos.get("temas_sensibles") or DEFAULTS_TEMPLATE["temas_sensibles"]
    reglas = datos.get("reglas_asistente") or DEFAULTS_TEMPLATE["reglas_asistente"]

    quien_lineas = []
    if edad and ciudad:
        quien_lineas.append(f"- {nombre}, {edad} años, vive en {ciudad}")
    elif edad:
        quien_lineas.append(f"- {nombre}, {edad} años")
    elif ciudad:
        quien_lineas.append(f"- {nombre}, vive en {ciudad}")
    else:
        quien_lineas.append(f"- {nombre}")
    if descripcion:
        quien_lineas.append(f"- {descripcion}")
    quien_lineas.append(f"- Al asistente lo conoce como {nombre_asistente}")

    return (
        f"# Perfil de {nombre}\n"
        "\n"
        "## Quién es\n"
        f"{chr(10).join(quien_lineas)}\n"
        "\n"
        "## Familia y contactos cercanos\n"
        f"{items_md(familiares)}\n"
        "\n"
        "## Gustos y temas que la alegran\n"
        f"{items_md(gustos)}\n"
        "\n"
        "## Salud (para contexto, no para diagnosticar)\n"
        f"{items_md(salud)}\n"
        "\n"
        "## Temas a manejar con cuidado\n"
        f"{items_md(temas)}\n"
        "\n"
        "## Reglas del asistente\n"
        f"{items_md(reglas)}\n"
        "\n"
        "## Aprendizajes\n"
        "\n"
        "## Ajustes sugeridos\n"
    )


# ---------------------------------------------------------------------------
# Wizard CLI — recolecta respuestas vía input()
# ---------------------------------------------------------------------------

def _wizard_cli(defaults: dict) -> dict:
    """
    Corre el cuestionario interactivo en consola. `defaults` son los
    valores sugeridos en cada pregunta (típicamente vienen de un
    `config.yml` o del state de un hogar).
    """
    # 1 · Identidad
    titulo("1 / 6  ·  Identidad")
    nombre = preguntar("¿Cómo se llama la persona?", defaults.get("nombre", ""))
    edad = preguntar("¿Cuántos años tiene?", defaults.get("edad", ""))
    ciudad = preguntar("¿En qué ciudad vive?", defaults.get("ciudad", ""))
    descripcion = preguntar(
        "Describila en una oración (personalidad, cómo es)",
        defaults.get("descripcion", ""),
    )
    nombre_asistente = preguntar(
        "¿Cómo se llama el asistente para ella?",
        defaults.get("nombre_asistente", "Aikiu"),
    )

    # 2 · Familia
    titulo("2 / 6  ·  Familia y contactos cercanos")
    print("\n  Ingresá cada familiar en una línea.")
    print("  Ejemplo: 'Hija Laura, vive en Buenos Aires, la visita los fines de semana'")
    familiares = preguntar_lista_libre("Familiares:")

    # 3 · Gustos
    titulo("3 / 6  ·  Gustos y temas que la alegran")
    gustos = preguntar_lista(
        "¿Qué temas o actividades la ponen contenta?",
        defaults.get("gustos") or [
            "La música y los tangos",
            "Recordar anécdotas de familia",
            "Programas de cocina en televisión",
            "Las plantas que tiene en casa",
        ],
    )

    # 4 · Salud
    titulo("4 / 6  ·  Salud  (solo contexto — el bot no diagnostica)")
    print("\n  Esta info ayuda al asistente a recordar medicamentos o limitaciones.")
    salud = preguntar_lista_libre("Notas de salud relevantes:")

    # 5 · Temas sensibles
    titulo("5 / 6  ·  Temas a manejar con cuidado")
    temas = preguntar_lista(
        "¿Qué temas deben tratarse con cuidado o evitarse?",
        defaults.get("temas_sensibles") or DEFAULTS_TEMPLATE["temas_sensibles"],
    )

    # 6 · Reglas del asistente
    titulo("6 / 6  ·  Reglas de comportamiento del asistente")
    reglas = preguntar_lista(
        "¿Cómo debe comportarse el asistente?",
        defaults.get("reglas_asistente") or DEFAULTS_TEMPLATE["reglas_asistente"],
    )

    return {
        "nombre": nombre,
        "edad": edad,
        "ciudad": ciudad,
        "descripcion": descripcion,
        "nombre_asistente": nombre_asistente,
        "familiares": familiares,
        "gustos": gustos,
        "salud": salud,
        "temas_sensibles": temas,
        "reglas_asistente": reglas,
    }


# ---------------------------------------------------------------------------
# Modos de operación
# ---------------------------------------------------------------------------

def _actualizar_config_global(nombre: str, nombre_asistente: str) -> Path:
    """Actualiza nombre_adulto_mayor y nombre_asistente en config.yml raíz."""
    config_path = BASE_DIR / "config.yml"
    contenido = config_path.read_text(encoding="utf-8")
    contenido = re.sub(
        r'^nombre_adulto_mayor:.*$',
        f'nombre_adulto_mayor: "{nombre}"',
        contenido,
        flags=re.MULTILINE,
    )
    contenido = re.sub(
        r'^nombre_asistente:.*$',
        f'nombre_asistente: "{nombre_asistente}"',
        contenido,
        flags=re.MULTILINE,
    )
    config_path.write_text(contenido, encoding="utf-8")
    return config_path


def _actualizar_state_hogar(chat_id: int, datos: dict) -> Path:
    """Mergea overrides multi-tenant (nombre_adulto_mayor, ciudad, etc.)
    en `instances/<chat_id>/state.json` sin pisar el resto del state."""
    from core import hogar as hogar_mod

    state_path = hogar_mod.state_path(chat_id)
    if state_path.exists():
        estado = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        estado = {"owner_chat_id": int(chat_id)}

    for clave, valor in (
        ("nombre_adulto_mayor", datos.get("nombre")),
        ("nombre_asistente", datos.get("nombre_asistente")),
        ("ciudad", datos.get("ciudad")),
    ):
        if valor:
            estado[clave] = valor

    estado["perfil_completo"] = True
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state_path


def _main_template():
    """Modo --template: regenera perfil.md y config.yml de la raíz."""
    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   Aikiu — Regenerar TEMPLATE neutro       ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()
    print("  Esto reescribe el template GLOBAL (perfil.md + config.yml).")
    print("  El template se usa solo como esqueleto inicial — los datos")
    print("  reales de cada adulto van en instances/<chat_id>/.")
    print()
    print("  Enter para regenerar con los defaults neutros,")
    print("  o ingresá valores para fijarlos en el template.")

    defaults = dict(DEFAULTS_TEMPLATE)
    datos = _wizard_cli(defaults)

    perfil_md = generar_perfil(datos)
    perfil_path = BASE_DIR / "perfil.md"
    perfil_path.write_text(perfil_md, encoding="utf-8")

    _actualizar_config_global(
        datos["nombre"] or "",
        datos["nombre_asistente"] or "Aikiu",
    )

    print()
    print(f"  ✓ Template guardado en {perfil_path.name}")
    print(f"  ✓ config.yml actualizado")
    print()
    if not datos["nombre"]:
        print("  Template NEUTRO (sin nombre): los hogares nuevos van a")
        print("  pasar por el wizard de onboarding en el primer /start.")
    print()


def _main_hogar(chat_id: int):
    """Modo --chat-id: configura un hogar existente."""
    from core import hogar as hogar_mod

    if not hogar_mod.existe_hogar(chat_id):
        print(
            f"\n  ✗ El hogar {chat_id} no existe en {hogar_mod.instances_root()}.\n"
            f"  El adulto tiene que mandar /start al bot principal primero.\n",
            file=sys.stderr,
        )
        sys.exit(2)

    estado = hogar_mod.leer_state(chat_id)
    defaults = {
        "nombre": estado.get("nombre_adulto_mayor") or estado.get("nombre_adulto") or "",
        "ciudad": estado.get("ciudad", ""),
        "nombre_asistente": estado.get("nombre_asistente", "Aikiu"),
    }

    print()
    print("  ╔═══════════════════════════════════════════╗")
    print(f"  ║   Configurar hogar {chat_id}".ljust(46) + "║")
    print("  ╚═══════════════════════════════════════════╝")
    print()
    print(f"  Vamos a armar el perfil del adulto del hogar {chat_id}.")
    print("  Si el hogar ya tiene datos, los vas a ver como defaults.")

    datos = _wizard_cli(defaults)

    perfil_md = generar_perfil(datos)
    perfil_path = hogar_mod.perfil_path(chat_id)
    perfil_path.parent.mkdir(parents=True, exist_ok=True)
    perfil_path.write_text(perfil_md, encoding="utf-8")

    state_path = _actualizar_state_hogar(chat_id, datos)

    print()
    print(f"  ✓ Perfil guardado en {perfil_path}")
    print(f"  ✓ State actualizado en {state_path}")
    print()


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="configurar.py",
        description=(
            "Configurar Aikiu. Sin flags o --template regenera el template "
            "neutro de la raíz. Con --chat-id <id> reconfigura un hogar "
            "existente (instances/<id>/)."
        ),
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--template",
        action="store_true",
        help="Regenerar el template neutro (perfil.md + config.yml de la raíz).",
    )
    grupo.add_argument(
        "--chat-id",
        type=int,
        metavar="ID",
        help="Reconfigurar el hogar con ese chat_id (instances/<id>/).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None):
    args = _parse_args(argv)
    if args.chat_id is not None:
        _main_hogar(args.chat_id)
    else:
        _main_template()


if __name__ == "__main__":
    main()
