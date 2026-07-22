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


def main():
    con = sqlite3.connect(DEST)
    con.executescript("""
        DROP TABLE IF EXISTS chunks;
        CREATE VIRTUAL TABLE chunks USING fts5(libro, pagina UNINDEXED, texto);
    """)
    total = 0
    for path in sorted(glob.glob(LIBROS + "/*.pdf")):
        lib = titulo(path)
        try:
            doc = fitz.open(path)
        except Exception as e:
            print(f"  ⚠️  {lib}: {e}"); continue
        filas, n = [], 0
        # Se acumula por página para conservar la cita (libro + página).
        for pg in range(len(doc)):
            t = doc[pg].get_text()
            if len(t.strip()) < 200:
                continue
            for tr in trozos(t):
                filas.append((lib, pg + 1, tr)); n += 1
        if not n:
            print(f"  ⚠️  {lib}: sin texto (¿escaneado?)"); continue
        con.executemany("INSERT INTO chunks VALUES (?,?,?)", filas)
        con.commit()
        total += n
        print(f"  {n:6d} chunks | {len(doc):4d} pg | {lib}")
    print(f"\n✓ {total} chunks indexados en {DEST}")
    con.close()


if __name__ == "__main__":
    main()
