"""
Asistente de configuración de Aikiu.
Genera perfil.md guiando al familiar sección por sección.
"""

import re
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).parent


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


def main():
    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   Aikiu — Configuración del perfil        ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()
    print("  Vamos a armar el perfil de la persona paso a paso.")
    print("  En cada pregunta podés presionar Enter para aceptar")
    print("  el valor sugerido, o escribir el tuyo.")

    config_path = BASE_DIR / "config.yml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ── 1 · Identidad ────────────────────────────────────
    titulo("1 / 6  ·  Identidad")

    nombre = preguntar("¿Cómo se llama la persona?",
                       config.get("nombre_adulto_mayor", "Marta"))
    edad = preguntar("¿Cuántos años tiene?", "83")
    ciudad = preguntar("¿En qué ciudad vive?", "Buenos Aires")
    descripcion = preguntar(
        "Describila en una oración (personalidad, cómo es)",
        "Es alegre, curiosa y le gusta charlar"
    )
    nombre_asistente = preguntar(
        "¿Cómo se llama el asistente para ella?",
        config.get("nombre_asistente", "Clara")
    )

    # ── 2 · Familia ──────────────────────────────────────
    titulo("2 / 6  ·  Familia y contactos cercanos")
    print("\n  Ingresá cada familiar en una línea.")
    print("  Ejemplo: 'Hija Laura, vive en Buenos Aires, la visita los fines de semana'")
    familiares = preguntar_lista_libre("Familiares:")
    if not familiares:
        familiares = ["(completar con los familiares cercanos)"]

    # ── 3 · Gustos ───────────────────────────────────────
    titulo("3 / 6  ·  Gustos y temas que la alegran")
    gustos = preguntar_lista(
        "¿Qué temas o actividades la ponen contenta?",
        [
            "La música y los tangos",
            "Recordar anécdotas de familia",
            "Programas de cocina en televisión",
            "Las plantas que tiene en casa",
        ]
    )

    # ── 4 · Salud ────────────────────────────────────────
    titulo("4 / 6  ·  Salud  (solo contexto — el bot no diagnostica)")
    print("\n  Esta info ayuda al asistente a recordar medicamentos o limitaciones.")
    salud = preguntar_lista_libre("Notas de salud relevantes:")
    if not salud:
        salud = ["Sin notas cargadas"]

    # ── 5 · Temas sensibles ──────────────────────────────
    titulo("5 / 6  ·  Temas a manejar con cuidado")
    temas = preguntar_lista(
        "¿Qué temas deben tratarse con cuidado o evitarse?",
        [
            "Guerras y conflictos: responder con calma y cambiar de tema",
            "Política: no opinar, redirigir a cómo está ella",
            "Catástrofes o muertes de famosos: calmar y redirigir",
            "Si suena triste o angustiada: contenerla con calidez y preguntar si necesita algo",
        ]
    )

    # ── 6 · Reglas del asistente ─────────────────────────
    titulo("6 / 6  ·  Reglas de comportamiento del asistente")
    reglas = preguntar_lista(
        "¿Cómo debe comportarse el asistente?",
        [
            "Oraciones muy cortas, simples y cálidas",
            "Español rioplatense natural, como un familiar cercano",
            "Nunca usar markdown ni símbolos — solo texto para escuchar",
            "Máximo 3 oraciones por respuesta",
            "Si no entiende algo, repetirlo de otra forma sin frustrarse",
            "Nunca dar detalles alarmantes sobre noticias del mundo",
        ]
    )

    # ── Generar perfil.md ─────────────────────────────────
    perfil = f"""# Perfil de {nombre}

## Quién es
- {nombre}, {edad} años, vive en {ciudad}
- {descripcion}
- Al asistente lo conoce como {nombre_asistente}

## Familia y contactos cercanos
{items_md(familiares)}

## Gustos y temas que la alegran
{items_md(gustos)}

## Salud (para contexto, no para diagnosticar)
{items_md(salud)}

## Temas a manejar con cuidado
{items_md(temas)}

## Reglas del asistente
{items_md(reglas)}
"""

    perfil_path = BASE_DIR / config.get("perfil", "perfil.md")
    perfil_path.write_text(perfil, encoding="utf-8")

    # ── Actualizar nombre en config.yml (preserva comentarios) ──
    contenido = config_path.read_text(encoding="utf-8")
    contenido = re.sub(r'^nombre_adulto_mayor:.*$', f'nombre_adulto_mayor: "{nombre}"',
                       contenido, flags=re.MULTILINE)
    contenido = re.sub(r'^nombre_asistente:.*$', f'nombre_asistente: "{nombre_asistente}"',
                       contenido, flags=re.MULTILINE)
    config_path.write_text(contenido, encoding="utf-8")

    print()
    print(f"  ✓ Perfil guardado en {perfil_path.name}")
    print(f"  ✓ config.yml actualizado")
    print()
    print("  Reiniciá el bot con:  bash start.sh")
    print()


if __name__ == "__main__":
    main()
