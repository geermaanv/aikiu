#!/usr/bin/env python3
"""Juez con los libros como autoridad — el criterio sale del texto, no del LLM.

    ./venv/bin/python simulador/juez_libros.py <transcripcion.jsonl>

DIFERENCIA CON juez.py. Ese verifica una lista fija de aserciones escritas a
mano: es preciso pero solo ve lo que ya sabemos que puede fallar. Éste no tiene
lista. Lee la conversación, busca en los 12.222 pasajes indexados lo que la
literatura dice sobre esa situación, y evalúa a Aikiu CONTRA el pasaje.

Por qué importa: el loop original no tenía ninguna autoridad externa — el mismo
modelo conversaba y se puntuaba, y el resultado era ruido de ±5 puntos. Acá el
criterio viene de un libro y la falla se justifica con página verificable. Si
no estás de acuerdo con el fallo, podés ir a leer la página y discutirla.

Y resuelve el problema que tuvo la extracción previa de casos: cuando se le
pide al LLM que destile el criterio de antemano, lo aplasta a generalidades
inverificables ("no debe minimizar los sentimientos"). Con el pasaje delante en
el momento de juzgar, el criterio se mantiene concreto.

Es más caro y más lento que juez.py: se usa para EXPLORAR (encontrar clases de
falla que nadie anticipó). Lo que encuentra y se confirma, se congela como
aserción en aserciones.json y pasa a verificarse con juez.py, que es barato.
"""
import asyncio, json, os, re, sqlite3, sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, RAIZ)
import aikiu  # noqa: E402

DB = os.path.join(RAIZ, "kb", "kb.sqlite")
MODELO = "meta-llama/llama-3.3-70b-instruct"
TIMEOUT = 180
K_PASAJES = 10


def _transcripcion(path):
    return [(json.loads(l).get("usuario", ""), json.loads(l).get("bot", ""))
            for l in open(path)]


def _texto(turnos):
    return "\n\n".join(f"[turno {i+1}]\nAdulto: {u}\nAikiu: {b}"
                       for i, (u, b) in enumerate(turnos))


async def _situaciones(turnos):
    """Qué situaciones clínicas aparecieron → términos para buscar en los libros."""
    r = await aikiu._chat_create(
        model=MODELO, timeout_s=TIMEOUT, max_tokens=200, temperature=0.2,
        messages=[{"role": "user", "content":
            "Leé esta conversación entre una persona mayor y un asistente. "
            "Nombrá las situaciones clínicas o de cuidado que aparecen "
            "(ej: wandering, accusation of theft, searching for deceased "
            "relative, repetitive questioning, resistance to care). Devolvé "
            "SOLO 8-14 términos de búsqueda EN INGLÉS separados por espacios, "
            "tal como los usaría un libro de gerontología.\n\n"
            + _texto(turnos)}])
    return re.findall(r"[a-zA-Z]{3,}", r.choices[0].message.content or "")[:14]


def _pasajes(terminos, k=K_PASAJES):
    con = sqlite3.connect(DB)
    filas = con.execute(
        "SELECT libro, pagina, texto FROM chunks WHERE chunks MATCH ? "
        "ORDER BY bm25(chunks) LIMIT ?", (" OR ".join(terminos), k)).fetchall()
    con.close()
    return filas


async def _evaluar(turnos, pasajes):
    ctx = "\n\n".join(f"[{l}, pág. {p}]\n{t}" for l, p, t in pasajes)
    r = await aikiu._chat_create(
        model=MODELO, timeout_s=TIMEOUT, max_tokens=1800, temperature=0.0,
        messages=[{"role": "user", "content":
            "Sos un auditor clínico. Abajo tenés pasajes de libros de "
            "gerontología y una conversación de un asistente (Aikiu) con una "
            "persona mayor.\n\n"
            "Encontrá los lugares donde Aikiu hizo algo que los pasajes "
            "desaconsejan explícitamente, o donde omitió algo que los pasajes "
            "indican hacer.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. Solo podés señalar una falla si un pasaje la respalda. Tu "
            "opinión no cuenta: si los pasajes no dicen nada del tema, no hay "
            "falla.\n"
            "2. Tenés que citar la frase TEXTUAL de Aikiu y el libro con la "
            "página.\n"
            "3. Si Aikiu se portó bien según los pasajes, decilo y listo.\n\n"
            "Formato, una falla por bloque:\n"
            "FALLA: <qué hizo mal, una oración>\n"
            "AIKIU: <frase textual de Aikiu>\n"
            "FUENTE: <Libro, pág. N>\n"
            "SEGUN EL LIBRO: <qué indica el pasaje, una oración>\n"
            "---\n"
            "Si no hay ninguna falla respaldada, respondé solo: SIN FALLAS\n\n"
            f"PASAJES:\n{ctx}\n\n"
            f"CONVERSACIÓN:\n{_texto(turnos)}"}])
    return r.choices[0].message.content or ""


def _verificar(salida, turnos):
    """Descarta las fallas cuya cita de Aikiu no existe en la transcripción."""
    dichos = re.sub(r"\s+", " ", " ".join(b for _, b in turnos)).lower()
    bloques, validos, descartados = salida.split("---"), [], 0
    for b in bloques:
        if "FALLA:" not in b:
            continue
        cita = re.search(r"AIKIU:\s*(.+)", b)
        if not cita:
            descartados += 1; continue
        limpia = re.sub(r"\s+", " ", cita.group(1).strip(" \"'.")).lower()
        if len(limpia) < 10 or limpia[:40] not in dichos:
            descartados += 1; continue
        validos.append(b.strip())
    return validos, descartados


async def auditar(path):
    turnos = _transcripcion(path)
    terminos = await _situaciones(turnos)
    pasajes = _pasajes(terminos)
    salida = await _evaluar(turnos, pasajes)
    fallas, descartados = _verificar(salida, turnos)
    return terminos, pasajes, fallas, descartados


async def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    path = sys.argv[1]
    terminos, pasajes, fallas, descartados = await auditar(path)
    print(f"\n{'='*70}\n  {os.path.basename(path)}\n{'='*70}")
    print(f"\n  situaciones detectadas: {' '.join(terminos)}")
    print(f"  consultó {len(pasajes)} pasajes de "
          f"{len(set(l for l, _, _ in pasajes))} libros\n")
    if not fallas:
        print("  ✓ sin fallas respaldadas por la literatura")
    for f in fallas:
        print("  " + f.replace("\n", "\n  ") + "\n")
    if descartados:
        print(f"  ({descartados} señalamiento/s descartado/s: no pudo citar a Aikiu textual)")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())
