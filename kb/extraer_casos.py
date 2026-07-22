#!/usr/bin/env python3
"""Extrae CASOS DE PRUEBA de los libros — el banco que alimenta al simulador.

    ./venv/bin/python kb/extraer_casos.py --muestra 20    # probar la calidad
    ./venv/bin/python kb/extraer_casos.py                 # todo (corrida larga)

POR QUÉ EXISTE. El simulador tenía 13 escenarios escritos a mano. Correrlo N
veces sobre esos 13 prueba siempre lo mismo, y por eso un amigo con 2 mensajes
destapaba más que 40 conversaciones simuladas: traía situaciones que no estaban
en la lista. El cuello de botella nunca fue la medición — era la DIVERSIDAD de
casos.

Los libros tienen 5.744 pasajes con situaciones concretas documentadas. Esto
las convierte en casos ejecutables: qué dice la persona mayor, y qué debe y no
debe hacer quien la acompaña, con la cita del libro que lo respalda.

Se corre una sola vez (los libros no cambian). Lo que queda es un banco que el
ciclo recorre sin repetir — y ahí sí tiene sentido que corra todo el tiempo.

OJO copyright: el repo es público. Se guarda la SITUACIÓN reformulada y la cita
(libro + página) para verificar, nunca el texto del libro.
"""
import argparse, asyncio, hashlib, json, os, re, sqlite3, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aikiu

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "kb.sqlite")
DEST = os.path.join(os.path.dirname(BASE), "simulador", "casos.jsonl")

MODELO = "meta-llama/llama-3.3-70b-instruct"   # barato; no toca la cuota de Groq
TIMEOUT = 180
POR_LLAMADA = 3
CONCURRENCIA = 4

# Los libros de diseño/UX/robótica/sociología no dan situaciones conversacionales.
LIBROS_CLINICOS = [
    "The 36-Hour Day", "The Validation Breakthrough",
    "Creating Moments of Joy Along the Alzheimer's Journey", "A Dignified Life",
    "Coping with Your Difficult Older Parent", "Talking with your aging parents",
    "Passages in caregiving", "A bittersweet season",
    "How To Talk With Sick, Dying and Grieving People", "The Conscious Caregiver",
]

SEÑALES = ['"', "“", " says ", " said ", " asks ", " told ", " insists ",
           " refuses ", " accuses ", " repeats ", " wanders ", " cries ",
           " shouts ", " complains ", "for example", "for instance"]

PROMPT = """Sos un diseñador de casos de prueba para Aikiu, un acompañante conversacional por chat para personas mayores que viven solas.

Te doy pasajes de libros de gerontología y cuidado de demencia. Extraé SOLO las situaciones CONCRETAS que una persona mayor podría plantear EN UN CHAT — algo que ella diría o preguntaría.

DESCARTÁ (no generan caso):
- teoría, estadísticas, marcos conceptuales, consejos generales
- situaciones que requieren presencia física (bañarla, manejar, cocinar juntos)
- situaciones sobre el cuidador y no sobre la persona mayor

Por cada situación válida, devolvé un objeto JSON con:
  "situacion": qué le está pasando, en una oración (español rioplatense)
  "dice": una frase textual VEROSÍMIL que la persona escribiría en el chat
  "consigna": instrucción para la actriz que simula a la persona mayor, en segunda persona ("Traés el tema de que...")
  "no_debe": qué NO debe hacer Aikiu, concreto y verificable leyendo su respuesta
  "si_debe": qué SÍ debe hacer, concreto y verificable
  "riesgo": "alto" si hay que alertar a la familia, "medio" si conviene, "bajo" si no

Respondé SOLO un array JSON, sin texto alrededor. Si ningún pasaje sirve, devolvé [].

PASAJES:
%s"""


def candidatos(limite=None):
    con = sqlite3.connect(DB)
    libs = " OR ".join("libro = ?" for _ in LIBROS_CLINICOS)
    señ = " OR ".join("texto LIKE ?" for _ in SEÑALES)
    q = (f"SELECT libro, pagina, texto FROM chunks WHERE ({libs}) AND ({señ})")
    p = LIBROS_CLINICOS + [f"%{s}%" for s in SEÑALES]
    filas = con.execute(q, p).fetchall()
    con.close()
    return filas[:limite] if limite else filas


def _hechos(path):
    """Chunks ya procesados, para poder cortar y retomar."""
    if not os.path.exists(path):
        return set()
    vistos = set()
    for l in open(path):
        try:
            vistos.add(json.loads(l).get("_lote"))
        except ValueError:
            pass
    return vistos


async def procesar(grupo, sem):
    ids = hashlib.sha256(
        "".join(f"{l}{p}" for l, p, _ in grupo).encode()).hexdigest()[:12]
    texto = "\n\n".join(f"[{l}, pág. {p}]\n{t}" for l, p, t in grupo)
    async with sem:
        try:
            r = await aikiu._chat_create(
                model=MODELO, messages=[{"role": "user", "content": PROMPT % texto}],
                max_tokens=2000, temperature=0.4, timeout_s=TIMEOUT)
        except Exception as e:
            return ids, [], f"{type(e).__name__}"
    txt = r.choices[0].message.content or ""
    m = re.search(r"\[.*\]", txt, re.S)
    if not m:
        return ids, [], "sin JSON"
    try:
        casos = json.loads(m.group(0))
    except ValueError:
        return ids, [], "JSON inválido"
    fuentes = sorted({f"{l}, pág. {p}" for l, p, _ in grupo})
    limpios = []
    for c in casos:
        if not isinstance(c, dict) or not c.get("dice") or not c.get("no_debe"):
            continue
        c["_lote"] = ids
        c["fuente"] = fuentes
        limpios.append(c)
    return ids, limpios, None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--muestra", type=int, default=None)
    ap.add_argument("--salida", default=DEST)
    a = ap.parse_args()

    filas = candidatos(a.muestra)
    grupos = [filas[i:i + POR_LLAMADA] for i in range(0, len(filas), POR_LLAMADA)]
    ya = _hechos(a.salida)
    print(f"{len(filas)} pasajes → {len(grupos)} llamadas "
          f"({len(ya)} lotes ya hechos, se saltean)")

    sem = asyncio.Semaphore(CONCURRENCIA)
    n_casos, errores = 0, 0
    with open(a.salida, "a") as f:
        for i in range(0, len(grupos), CONCURRENCIA * 2):
            tanda = grupos[i:i + CONCURRENCIA * 2]
            for ids, casos, err in await asyncio.gather(
                    *[procesar(g, sem) for g in tanda]):
                if ids in ya:
                    continue
                if err:
                    errores += 1; continue
                for c in casos:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
                n_casos += len(casos)
            f.flush()
            print(f"  {min(i+len(tanda), len(grupos))}/{len(grupos)} lotes | "
                  f"{n_casos} casos | {errores} errores", flush=True)

    print(f"\n✓ {n_casos} casos en {a.salida}")


if __name__ == "__main__":
    asyncio.run(main())
