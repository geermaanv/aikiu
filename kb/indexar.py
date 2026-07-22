#!/usr/bin/env python3
"""Indexa los libros de kb-adults en SQLite FTS5 — reemplazo local de NotebookLM.

Se corre UNA vez (y de nuevo solo si se agregan libros):
    ./venv/bin/python kb/indexar.py

Genera kb/kb.sqlite (gitignoreado: los libros tienen copyright, el índice
contiene su texto). Consultar con kb/preguntar.py.
"""
import fitz, glob, os, re, sqlite3, sys

LIBROS = "/Users/germanv/proyectos/kb-adults/raw files"
DEST = os.path.join(os.path.dirname(__file__), "kb.sqlite")
CHUNK, SOLAPE = 1500, 200


def titulo(path):
    """'A Dignified Life_ The Best Friends -- Bell MSW...' → 'A Dignified Life'."""
    n = os.path.basename(path).replace(".pdf", "")
    return re.split(r"\s+--\s+|_ ", n)[0].strip()[:70]


def trozos(texto):
    texto = re.sub(r"\s+", " ", texto).strip()
    i = 0
    while i < len(texto):
        yield texto[i:i + CHUNK]
        i += CHUNK - SOLAPE


def es_paratexto(t):
    """¿Es índice alfabético, tabla de contenidos o bibliografía?

    Estas páginas son listas de palabras sueltas con números de página, así que
    matchean CUALQUIER consulta y ganan siempre por BM25. Buscando sobre una
    charla de búsqueda de un familiar fallecido, el top-5 traía
    'Nursing homes, 19-20, 168-181' en vez del pasaje de Feil. Filtrarlas es el
    arreglo más barato y de mayor impacto en la recuperación.
    """
    if len(t) < 120:
        return True
    digitos = sum(c.isdigit() for c in t) / len(t)
    comas = t.count(",") / max(len(t.split()), 1)
    # Un índice tiene muchísimos dígitos y comas y casi ningún punto final.
    oraciones = len(re.findall(r"[a-z]{3,}\.\s+[A-Z]", t))
    if digitos > 0.06 and comas > 0.09 and oraciones < 3:
        return True
    # Puntos de relleno de una tabla de contenidos: "Chapter 3 . . . . . 47"
    if len(re.findall(r"\.\s?\.\s?\.", t)) > 3:
        return True
    # Bibliografía: muchos años entre paréntesis o patrones "Apellido, N."
    if len(re.findall(r"\(19\d\d\)|\(20\d\d\)", t)) > 4:
        return True
    return False


def main():
    con = sqlite3.connect(DEST)
    con.executescript("""
        DROP TABLE IF EXISTS chunks;
        CREATE VIRTUAL TABLE chunks USING fts5(libro, pagina UNINDEXED, texto);
    """)
    total, descartados_tot = 0, 0
    for path in sorted(glob.glob(LIBROS + "/*.pdf")):
        lib = titulo(path)
        try:
            doc = fitz.open(path)
        except Exception as e:
            print(f"  ⚠️  {lib}: {e}"); continue
        filas, n, descartados = [], 0, 0
        # Se acumula por página para conservar la cita (libro + página).
        for pg in range(len(doc)):
            t = doc[pg].get_text()
            if len(t.strip()) < 200:
                continue
            for tr in trozos(t):
                if es_paratexto(tr):
                    descartados += 1; continue
                filas.append((lib, pg + 1, tr)); n += 1
        if not n:
            print(f"  ⚠️  {lib}: sin texto (¿escaneado?)"); continue
        con.executemany("INSERT INTO chunks VALUES (?,?,?)", filas)
        con.commit()
        total += n
        descartados_tot += descartados
        print(f"  {n:6d} chunks | {descartados:5d} descartados | {lib}")
    print(f"\n✓ {total} chunks indexados ({descartados_tot} de paratexto descartados) en {DEST}")
    con.close()


if __name__ == "__main__":
    main()
