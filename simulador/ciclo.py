#!/usr/bin/env python3
"""Ciclo de mejora: N conversaciones × M escenarios → juez → tasas de falla.

    ./venv/bin/python simulador/ciclo.py            # todos los escenarios, 3 reps
    ./venv/bin/python simulador/ciclo.py -n 5       # 5 repeticiones
    ./venv/bin/python simulador/ciclo.py -e caida buscar_fallecido
    ./venv/bin/python simulador/ciclo.py --comparar # contra la corrida anterior

Qué lo hace distinto del loop viejo (simulador/loop.py, notas 0-10):

  · Aserciones binarias, no puntajes. El juez viejo daba ±5 puntos de varianza
    en el mismo texto; éste dio 8/8 idéntico en 5 corridas.
  · Con N repeticiones, la salida es una TASA ("A3 falla en 4 de 10"), que sí es
    comparable entre corridas y ordena por dónde arrancar.
  · Guarda histórico en simulador/historial_ciclos.jsonl → detecta REGRESIONES:
    una aserción que pasaba y ahora falla es la señal más valiosa, y es
    justamente la que un puntaje promedio esconde.

Lo que este ciclo NO hace, a propósito: escribir reglas solo en aikiu_core.md.
Diagnostica y prioriza; el parche lo decidís vos. En este proyecto ya pasó dos
veces que una regla nueva rompió una vieja en silencio, y el núcleo tuvo que
podarse de 92 a 76 reglas. Un loop que se autoedita siempre agrega y nunca poda.
"""
import argparse, asyncio, collections, json, os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, RAIZ)
sys.path.insert(0, BASE)
from juez import juzgar, aserciones_de  # noqa: E402

HISTORIAL = os.path.join(BASE, "historial_ciclos.jsonl")
PY = os.path.join(RAIZ, "venv", "bin", "python")


def _correr_simulacion(persona, turnos, escenario, dest):
    """Corre el simulador y devuelve la ruta del .jsonl generado."""
    with open(os.devnull, "w") as null:
        subprocess.run(
            [PY, os.path.join(BASE, "simulador.py"), persona, str(turnos), escenario],
            cwd=RAIZ, stdout=null, stderr=null, timeout=900)
    logs = sorted((os.path.join(BASE, "logs", f) for f in os.listdir(os.path.join(BASE, "logs"))
                   if f.startswith("iter") and f.endswith(".jsonl")),
                  key=os.path.getmtime)
    if not logs:
        return None
    os.replace(logs[-1], dest)
    return dest


async def ciclo(escenarios, reps, persona, turnos):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest_dir = os.path.join(BASE, "logs", f"ciclo_{stamp}")
    os.makedirs(dest_dir, exist_ok=True)
    # {aserción: [n_fallas, n_corridas]}
    tally = collections.defaultdict(lambda: [0, 0])
    evidencias = collections.defaultdict(list)

    for esc in escenarios:
        print(f"\n▸ {esc}", flush=True)
        for i in range(reps):
            dest = os.path.join(dest_dir, f"{esc}_{i+1}.jsonl")
            if not _correr_simulacion(persona, turnos, esc, dest):
                print(f"  rep {i+1}: no generó log"); continue
            res, ases = await juzgar(dest, esc)
            fallas = [a["id"] for a in ases if res[a["id"]]["falla"]]
            for a in ases:
                clave = f"{esc}:{a['id']}" if a["id"].startswith("S-") else a["id"]
                tally[clave][1] += 1
                if res[a["id"]]["falla"]:
                    tally[clave][0] += 1
                    ev = res[a["id"]].get("cita", "")
                    if ev and len(evidencias[clave]) < 3:
                        evidencias[clave].append(ev)
            print(f"  rep {i+1}: {len(ases)-len(fallas)}/{len(ases)} ok"
                  + (f"  ✗ {', '.join(fallas)}" if fallas else ""), flush=True)

    return stamp, dest_dir, tally, evidencias


def _previo(campo="tasas"):
    if not os.path.exists(HISTORIAL):
        return {}
    lineas = [l for l in open(HISTORIAL) if l.strip()]
    return json.loads(lineas[-1]).get(campo, {}) if lineas else {}


def _previo_n():
    """Cuántas corridas midió el ciclo anterior por aserción. Sin esto no se
    puede distinguir 'antes pasaba' de 'antes no se medía'."""
    return _previo("n")


def reportar(stamp, dest_dir, tally, evidencias, comparar):
    prev = _previo() if comparar else {}
    tasas = {k: v[0] / v[1] for k, v in tally.items() if v[1]}

    print(f"\n{'='*66}\n  CICLO {stamp} — {dest_dir}\n{'='*66}")
    fallando = sorted(((k, v) for k, v in tasas.items() if v > 0),
                      key=lambda x: -x[1])
    if not fallando:
        print("\n  ✓ ninguna aserción falló")
    else:
        print(f"\n  Aserciones que fallan (ordenadas por frecuencia):\n")
        for k, tasa in fallando:
            n, tot = tally[k]
            delta = ""
            if k in prev:
                d = tasa - prev[k]
                delta = f"  ({'▲' if d > 0 else '▼'}{abs(d)*100:.0f}pp vs. ciclo anterior)" if abs(d) > 0.01 else "  (igual)"
            elif prev:
                delta = "  (nueva)"
            print(f"  ✗ {k:24s} {n}/{tot} corridas {delta}")
            for ev in evidencias[k][:2]:
                print(f"       \"{ev[:110]}\"")

    # Regresiones: pasaba antes, falla ahora. La señal más cara de perder.
    #
    # Solo vale comparar si el ciclo anterior midió esa aserción con un alcance
    # parecido. El 22/07 el reporte cantó "REGRESIONES: G1, G3, G5, G7" cuando
    # en realidad el ciclo previo había corrido 2 escenarios × 2 reps y éste 13
    # × 5: nunca habían pasado, simplemente no se habían medido. Un falso aviso
    # de regresión manda a buscar un culpable que no existe.
    prev_n = _previo_n() if comparar else {}
    regres = [k for k, t in tasas.items()
              if t > 0 and prev.get(k, 1) == 0
              and prev_n.get(k, 0) >= tally[k][1] * 0.5]
    if regres:
        print(f"\n  ⚠️  REGRESIONES (pasaban en el ciclo anterior): {', '.join(regres)}")
    arreglados = [k for k, t in prev.items() if t > 0 and tasas.get(k, 1) == 0]
    if arreglados:
        print(f"  ✓ Arreglados desde el ciclo anterior: {', '.join(arreglados)}")

    with open(HISTORIAL, "a") as f:
        f.write(json.dumps({"stamp": stamp, "tasas": tasas,
                            "n": {k: v[1] for k, v in tally.items()}}) + "\n")
    print(f"\n  Histórico: {HISTORIAL}\n{'='*66}")


def gate(tally, nivel, niveles):
    """Veredicto BINARIO: ¿se gana el nivel o se sigue en el loop?

    Sin promedios ni umbrales blandos: una sola falla en cualquier aserción
    deja el nivel en rojo. Un criterio con tolerancia ('95% de las corridas')
    se vuelve negociable, y lo que se negocia no cierra nunca.

    Devuelve (pasa: bool, culpables: list).
    """
    culpables = sorted(k for k, (f, t) in tally.items() if t and f > 0)
    return not culpables, culpables


def _niveles_a_correr(objetivo, niveles):
    """El nivel objetivo MÁS todos los anteriores: los ganados se reverifican
    siempre, si no el arreglo de hoy rompe en silencio lo de la semana pasada."""
    return [n for n in niveles if n["n"] <= objetivo]


async def main():
    cfg = json.load(open(os.path.join(BASE, "niveles.json")))
    niveles = cfg["niveles"]
    ap = argparse.ArgumentParser()
    ap.add_argument("-l", "--nivel", type=int, default=cfg["estado"]["nivel_actual"],
                    help="nivel objetivo (corre ése y todos los anteriores)")
    ap.add_argument("-n", "--reps", type=int, default=None, help="pisa las reps del nivel")
    ap.add_argument("-p", "--persona", default="marta")
    ap.add_argument("-t", "--turnos", type=int, default=8)
    ap.add_argument("--comparar", action="store_true", default=True)
    a = ap.parse_args()

    a_correr = _niveles_a_correr(a.nivel, niveles)
    total_tally, total_ev, stamp, dest = collections.defaultdict(lambda: [0, 0]), \
        collections.defaultdict(list), None, None
    veredictos = []

    for niv in a_correr:
        reps = a.reps or niv["reps"]
        print(f"\n{'─'*66}\n  NIVEL {niv['n']} — {niv['nombre']}  "
              f"({len(niv['escenarios'])} escenarios × {reps} reps)\n"
              f"  {niv['criterio']}\n{'─'*66}")
        stamp, dest, tally, ev = await ciclo(niv["escenarios"], reps, a.persona, a.turnos)
        pasa, culpables = gate(tally, niv, niveles)
        veredictos.append((niv, pasa, culpables))
        for k, v in tally.items():
            total_tally[k][0] += v[0]; total_tally[k][1] += v[1]
        for k, v in ev.items():
            total_ev[k].extend(v)

    reportar(stamp, dest, total_tally, total_ev, a.comparar)

    print(f"\n{'═'*66}\n  VEREDICTO\n{'═'*66}")
    for niv, pasa, culpables in veredictos:
        print(f"  {'🟢 PASA ' if pasa else '🔴 FALLA'}  nivel {niv['n']} — {niv['nombre']}"
              + ("" if pasa else f"   ← {', '.join(culpables)}"))

    todos_ok = all(p for _, p, _ in veredictos)
    objetivo = a_correr[-1]
    if todos_ok:
        siguiente = next((n for n in niveles if n["n"] == objetivo["n"] + 1), None)
        print(f"\n  ✅ Nivel {objetivo['n']} GANADO."
              + (f" Subí a nivel {siguiente['n']} ({siguiente['nombre']}):\n"
                 f"     actualizá nivel_actual en simulador/niveles.json y corré de nuevo."
                 if siguiente else " No quedan niveles: al gate con Irene."))
    else:
        rotos = [n['n'] for n, p, _ in veredictos if not p]
        print(f"\n  ⛔ Seguís en el loop. Nivel(es) en rojo: {rotos}."
              f"\n     Arreglá la regla, corré de nuevo. No subas de nivel hasta el verde.")
    print(f"{'═'*66}")
    sys.exit(0 if todos_ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
