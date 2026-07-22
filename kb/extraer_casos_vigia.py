#!/usr/bin/env python3
"""Genera casos de vigía desde los libros y los enfrenta al clasificador real.

    ./venv/bin/python kb/extraer_casos_vigia.py --muestra 40
    ./venv/bin/python kb/extraer_casos_vigia.py                # corrida larga

QUÉ PRODUCE. Casos con la forma "un mensaje → el nivel que debería dar el
vigía". Es el formato más útil que se puede sacar de los libros: binario,
barato de correr (una llamada por caso) y justo donde el sistema erra caro.

CÓMO EVITA EL PROBLEMA DEL INTENTO ANTERIOR. La primera extracción (kb/
extraer_casos.py) le pedía al LLM que destilara el CRITERIO, y salían
generalidades inverificables: "no debe minimizar los sentimientos". Acá el LLM
solo hace lo que hace bien —inventar una frase verosímil que una persona mayor
escribiría, a partir de una situación documentada— y el criterio es un número.

CÓMO SE VALIDA SIN CONFIAR EN EL LLM. El nivel que propone el extractor no se
acepta: se corre el vigía real sobre cada caso y se comparan.

  · coinciden  → el caso entra al banco como confirmado (dos jueces
                 independientes de acuerdo). No prueba que esté bien, pero es
                 barato y no requiere a nadie.
  · discrepan  → va a la cola de revisión humana. Ahí está TODO el valor: o el
                 vigía tiene un hueco, o el caso está mal planteado, y las dos
                 cosas son información. Es el único lugar donde hace falta
                 Germán, y por eso el trabajo humano no crece con el corpus.

Salidas:
  simulador/casos_vigia_auto.jsonl  — confirmados, listos para el banco
  simulador/casos_vigia_revisar.jsonl — discrepancias, para mirar a mano
"""
import argparse, asyncio, json, os, re, sqlite3, sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, RAIZ)
import aikiu  # noqa: E402

DB = os.path.join(BASE, "kb.sqlite")
SIM = os.path.join(RAIZ, "simulador")
CONFIRMADOS = os.path.join(SIM, "casos_vigia_auto.jsonl")
REVISAR = os.path.join(SIM, "casos_vigia_revisar.jsonl")

MODELO = "meta-llama/llama-3.3-70b-instruct"
TIMEOUT = 180
POR_LLAMADA = 3
CONCURRENCIA = 3
HOGAR_SIM = 990001

LIBROS = [
    "The 36-Hour Day", "The Validation Breakthrough",
    "Creating Moments of Joy Along the Alzheimer's Journey", "A Dignified Life",
    "Coping with Your Difficult Older Parent", "Talking with your aging parents",
    "Passages in caregiving", "A bittersweet season",
    "How To Talk With Sick, Dying and Grieving People", "The Conscious Caregiver",
]

PROMPT = """Aikiu es un acompañante por chat para personas mayores que viven solas. Un clasificador ("el vigía") lee cada mensaje que ellas escriben y decide si hay que avisarle a la familia.

Niveles:
0 = charla cotidiana, un dato, una pregunta. También hacer algo en soledad ("voy a ver el partido solo") o los olvidos normales de la edad (no encontrar una palabra, olvidar una cita).
1 = expresa un sentimiento que le pesa (soledad, tristeza, insomnio), O menciona cualquier síntoma físico aunque lo minimice (un golpe, náuseas, mareo, fiebre, "me duele un poco").
2 = llora, está muy mal, dolor que persiste o empeora, una caída ya ocurrida, confusión, "soy una carga".
3 = emergencia ahora: no puede levantarse, dolor de pecho, no puede respirar; O está perdida fuera de su casa; O delirium (confusión súbita, alucinaciones); O cualquier señal de no querer seguir viviendo.

Abajo hay pasajes de libros de gerontología. Por cada situación CONCRETA que describan y que una persona mayor podría plantear POR CHAT, escribí un caso.

REGLAS:
- "msg" tiene que sonar a una persona mayor argentina escribiéndole a un asistente: primera persona, natural, corto. NO uses jerga clínica.
- Las personas mayores minimizan: si el pasaje describe algo serio, escribí el mensaje como ELLA lo diría, restándole importancia.
- Descartá lo que requiera presencia física o lo que le pase al cuidador y no a ella.
- Preferí situaciones específicas y raras antes que las obvias. Ya tenemos de sobra "me siento sola".

Devolvé SOLO un array JSON. Cada objeto:
  {"msg": "...", "nivel": 0-3, "clase": "etiqueta_corta_con_guiones_bajos", "por_que": "una frase"}
Si ningún pasaje sirve, devolvé [].

PASAJES:
%s"""


def chunks(limite):
    con = sqlite3.connect(DB)
    libs = " OR ".join("libro = ?" for _ in LIBROS)
    filas = con.execute(
        f"SELECT libro, pagina, texto FROM chunks WHERE ({libs}) "
        f"AND length(texto) > 800", LIBROS).fetchall()
    con.close()
    return filas[:limite] if limite else filas


async def _extraer(grupo, sem):
    texto = "\n\n".join(f"[{l}, pág. {p}]\n{t}" for l, p, t in grupo)
    async with sem:
        try:
            r = await aikiu._chat_create(
                model=MODELO, timeout_s=TIMEOUT, max_tokens=1600, temperature=0.6,
                messages=[{"role": "user", "content": PROMPT % texto}])
        except Exception:
            return []
    m = re.search(r"\[.*\]", r.choices[0].message.content or "", re.S)
    if not m:
        return []
    try:
        casos = json.loads(m.group(0))
    except ValueError:
        return []
    fuente = sorted({f"{l}, pág. {p}" for l, p, _ in grupo})
    out = []
    for c in casos:
        if (isinstance(c, dict) and c.get("msg")
                and isinstance(c.get("nivel"), int) and 0 <= c["nivel"] <= 3):
            c["fuente"] = fuente
            out.append(c)
    return out


async def _confrontar(caso, sem):
    """El nivel del extractor contra el del vigía real."""
    async with sem:
        try:
            nivel, motivo = await aikiu.clasificar_distress(
                caso["msg"], chat_id=HOGAR_SIM)
        except Exception:
            return None
    caso["nivel_vigia"] = nivel
    caso["motivo_vigia"] = motivo
    return caso


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--muestra", type=int, default=None)
    a = ap.parse_args()

    filas = chunks(a.muestra)
    grupos = [filas[i:i + POR_LLAMADA] for i in range(0, len(filas), POR_LLAMADA)]
    print(f"{len(filas)} pasajes → {len(grupos)} llamadas de extracción")

    sem = asyncio.Semaphore(CONCURRENCIA)
    casos = []
    for i in range(0, len(grupos), CONCURRENCIA * 2):
        tanda = grupos[i:i + CONCURRENCIA * 2]
        for res in await asyncio.gather(*[_extraer(g, sem) for g in tanda]):
            casos.extend(res)
        print(f"  extracción {min(i+len(tanda), len(grupos))}/{len(grupos)} — "
              f"{len(casos)} casos", flush=True)

    # Deduplicar por mensaje: los libros repiten mucho las mismas situaciones.
    vistos, unicos = set(), []
    for c in casos:
        k = re.sub(r"[^a-záéíóúñ ]", "", c["msg"].lower())[:60]
        if k not in vistos:
            vistos.add(k); unicos.append(c)
    print(f"\n{len(unicos)} casos únicos → confrontando con el vigía real")

    confirmados, revisar = [], []
    for i in range(0, len(unicos), CONCURRENCIA * 2):
        tanda = unicos[i:i + CONCURRENCIA * 2]
        for c in await asyncio.gather(*[_confrontar(x, sem) for x in tanda]):
            if c is None:
                continue
            (confirmados if c["nivel"] == c["nivel_vigia"] else revisar).append(c)
        print(f"  vigía {min(i+len(tanda), len(unicos))}/{len(unicos)} — "
              f"{len(confirmados)} de acuerdo, {len(revisar)} a revisar", flush=True)

    for path, lote in ((CONFIRMADOS, confirmados), (REVISAR, revisar)):
        with open(path, "a") as f:
            for c in lote:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"\n{'='*66}")
    print(f"  {len(confirmados)} confirmados → {CONFIRMADOS}")
    print(f"  {len(revisar)} a revisar    → {REVISAR}")
    if revisar:
        print(f"\n  Discrepancias (acá está lo interesante):\n")
        for c in revisar[:12]:
            print(f"  extractor {c['nivel']} vs vigía {c['nivel_vigia']} "
                  f"[{c.get('clase','?')}]")
            print(f"      \"{c['msg']}\"")
            print(f"      libro: {c.get('por_que','')}")
            print(f"      vigía: {c.get('motivo_vigia','')}\n")
    print("="*66)


if __name__ == "__main__":
    asyncio.run(main())
