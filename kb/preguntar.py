#!/usr/bin/env python3
"""Pregunta a los libros — reemplazo local de NotebookLM, con citas.

    ./venv/bin/python kb/preguntar.py "¿cómo se responde a una acusación de robo?"
    ./venv/bin/python kb/preguntar.py --lote kb/preguntas.txt   # una por línea

Circuito: pregunta en español → GLM arma los términos de búsqueda en inglés
(los libros están en inglés) → FTS5/BM25 trae los pasajes → GLM sintetiza en
español citando libro y página.

OJO: la salida se destila con palabras propias en simulador/conversaciones.md.
No pegar los pasajes textuales en el repo — es público y los libros tienen
copyright. Las citas (libro + página) sí, sirven para verificar.
"""
import asyncio, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aikiu

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb.sqlite")
K = 14


async def _terminos(pregunta):
    """Español → términos de búsqueda en inglés (los libros están en inglés)."""
    r = await aikiu._chat_create(
        model=aikiu.CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content":
            "Sos un bibliotecario. Traducí esta consulta a 10-16 términos de "
            "búsqueda en INGLÉS para buscar en libros de gerontología, demencia "
            "y cuidado de adultos mayores. Incluí los términos técnicos que "
            "usarían esos libros. Devolvé SOLO las palabras separadas por "
            f"espacios, sin comillas ni explicación.\n\nConsulta: {pregunta}"}],
        max_tokens=120, temperature=0.2)
    t = r.choices[0].message.content.strip()
    return [w for w in re.findall(r"[a-zA-Z]{3,}", t)][:16]


def _buscar(terminos, k=K):
    con = sqlite3.connect(DB)
    q = " OR ".join(terminos)
    filas = con.execute(
        "SELECT libro, pagina, texto FROM chunks WHERE chunks MATCH ? "
        "ORDER BY bm25(chunks) LIMIT ?", (q, k)).fetchall()
    con.close()
    return filas


async def _sintetizar(pregunta, filas):
    ctx = "\n\n".join(
        f"[{i+1}] {lib}, pág. {pg}:\n{txt}" for i, (lib, pg, txt) in enumerate(filas))
    r = await aikiu._chat_create(
        model=aikiu.CONFIG.get("modelo_llm", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content":
            "Sos un experto en gerontología que asesora el diseño de un "
            "acompañante conversacional para adultos mayores. Respondé la "
            "pregunta USANDO SOLO los pasajes de abajo. En español rioplatense, "
            "concreto y accionable: qué dice o hace la persona mayor, y qué debe "
            "hacer y NO hacer quien la acompaña. Citá la fuente como "
            "(Libro, pág. N) al final de cada afirmación importante. Si los "
            "pasajes no alcanzan para responder, decilo explícitamente.\n\n"
            f"PREGUNTA: {pregunta}\n\nPASAJES:\n{ctx}"}],
        max_tokens=1600, temperature=0.3)
    return r.choices[0].message.content.strip()


async def responder(pregunta):
    terminos = await _terminos(pregunta)
    filas = _buscar(terminos)
    if not filas:
        return f"Sin resultados para: {terminos}"
    fuentes = sorted({f"{lib} (pág. {pg})" for lib, pg, _ in filas})
    cuerpo = await _sintetizar(pregunta, filas)
    return f"{cuerpo}\n\n---\n**Pasajes consultados:** {'; '.join(fuentes)}"


async def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    if args[0] == "--lote":
        preguntas = [l.strip() for l in open(args[1]) if l.strip()
                     and not l.startswith("#")]
    else:
        preguntas = [" ".join(args)]
    for p in preguntas:
        print(f"\n{'='*70}\n## {p}\n{'='*70}\n")
        print(await responder(p))


if __name__ == "__main__":
    asyncio.run(main())
