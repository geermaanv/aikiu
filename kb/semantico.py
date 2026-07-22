#!/usr/bin/env python3
"""Búsqueda semántica multilingüe sobre los libros.

    ./venv/bin/python kb/semantico.py --construir        # una vez, ~10 min
    ./venv/bin/python kb/semantico.py "busca a su mamá que ya murió"

POR QUÉ. La búsqueda léxica (FTS5/BM25 de kb/indexar.py) no cruza idiomas ni
entiende significado. Consultando en español sobre una charla donde Aikiu le
sigue la mentira a alguien que busca a su madre muerta, el top-5 traía teoría
genérica sobre demencia — el pasaje que lo condena (Feil, pág. 89: "they do not
trust caregivers who pretend to agree with them") no comparte NINGUNA palabra
con la consulta.

Se probaron dos parches antes de esto y los dos fallaron: traducir la consulta
al inglés con un LLM (frágil — se le colaba español y envenenaba la búsqueda) y
filtrar el paratexto (necesario, pero insuficiente).

El modelo multilingüe mapea español e inglés al mismo espacio vectorial, así
que la frontera de idioma desaparece: se consulta en español, se encuentra en
inglés, sin traducir nada. Corre local por ONNX, sin torch y sin API.
"""
import argparse, json, os, sqlite3, sys

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "kb.sqlite")
VECTORES = os.path.join(BASE, "vectores.npy")
META = os.path.join(BASE, "vectores_meta.json")

MODELO = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
LOTE = 64


def _modelo():
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=MODELO)


def construir():
    con = sqlite3.connect(DB)
    filas = con.execute("SELECT libro, pagina, texto FROM chunks").fetchall()
    con.close()
    print(f"{len(filas)} chunks — cargando {MODELO} (la primera vez lo descarga)")
    emb = _modelo()
    textos = [t for _, _, t in filas]
    vecs = []
    for i, v in enumerate(emb.embed(textos, batch_size=LOTE)):
        vecs.append(v)
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{len(textos)}", flush=True)
    M = np.array(vecs, dtype=np.float32)
    M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9   # coseno = producto
    np.save(VECTORES, M)
    json.dump([[l, p] for l, p, _ in filas], open(META, "w"))
    print(f"\n✓ {M.shape[0]} vectores de {M.shape[1]} dims → {VECTORES}")


_cache = {}


def buscar(consulta, k=10):
    """Devuelve [(libro, pagina, texto, score)] por similitud semántica."""
    if "M" not in _cache:
        _cache["M"] = np.load(VECTORES)
        _cache["meta"] = json.load(open(META))
        _cache["emb"] = _modelo()
    q = next(iter(_cache["emb"].embed([consulta])))
    q = np.asarray(q, dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-9
    sims = _cache["M"] @ q
    idx = np.argpartition(-sims, k)[:k]
    idx = idx[np.argsort(-sims[idx])]

    con = sqlite3.connect(DB)
    textos = [r[0] for r in con.execute("SELECT texto FROM chunks")]
    con.close()
    return [(_cache["meta"][i][0], _cache["meta"][i][1], textos[i], float(sims[i]))
            for i in idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--construir", action="store_true")
    ap.add_argument("consulta", nargs="*")
    a = ap.parse_args()
    if a.construir:
        construir(); return
    if not a.consulta:
        print(__doc__); return
    for lib, pg, t, s in buscar(" ".join(a.consulta)):
        print(f"  [{s:.3f}] {lib}, pág. {pg}\n      {t[:230]}...\n")


if __name__ == "__main__":
    main()
