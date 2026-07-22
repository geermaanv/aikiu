#!/usr/bin/env python3
"""Corre el banco de casos del vigía — la verificación más binaria del sistema.

    ./venv/bin/python simulador/correr_vigia.py            # todos
    ./venv/bin/python simulador/correr_vigia.py -c delirium ideacion_suicida
    ./venv/bin/python simulador/correr_vigia.py -n 3       # 3 veces cada caso

Un mensaje entra, un número sale, y hay un número correcto. No hace falta
juzgar una conversación entera ni interpretar nada: el caso pasa o no pasa.
Por eso es ~40x más barato que un ciclo del simulador y se puede correr después
de cada cambio del prompt del vigía.

Y cubre lo más caro que el sistema puede errar en las dos direcciones:
  · falso negativo — no avisar de una emergencia real (V3xx)
  · falso positivo — quemar a la familia con alertas por nada (V0xx), que hace
    que dejen de mirar el bot y termina costando la alerta que sí importaba

Sale con código 0 si pasan todos, 1 si falla alguno: sirve como gate.

Los niveles adyacentes NO son equivalentes, pero no pesan igual: clasificar una
emergencia como nivel 2 (la familia se entera igual, tarde) es distinto de
clasificarla 0 (nadie se entera nunca). El reporte los separa.
"""
import argparse, asyncio, collections, json, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(BASE)
sys.path.insert(0, RAIZ)
import aikiu  # noqa: E402

CASOS = os.path.join(BASE, "casos_vigia.jsonl")
HOGAR_SIM = 990001
CONCURRENCIA = 3


def cargar(clases=None):
    casos = []
    for l in open(CASOS):
        l = l.strip()
        if not l:
            continue
        d = json.loads(l)
        if "_doc" in d:
            continue
        if clases and d.get("clase") not in clases:
            continue
        casos.append(d)
    return casos


async def _uno(caso, sem):
    async with sem:
        try:
            nivel, motivo = await aikiu.clasificar_distress(
                caso["msg"], chat_id=HOGAR_SIM)
        except Exception as e:
            return caso, None, f"{type(e).__name__}: {e}"
    return caso, nivel, motivo


async def correr(casos, reps):
    sem = asyncio.Semaphore(CONCURRENCIA)
    tareas = [_uno(c, sem) for c in casos for _ in range(reps)]
    return await asyncio.gather(*tareas)


def reportar(resultados):
    por_caso = collections.defaultdict(list)
    motivos = {}
    for caso, nivel, motivo in resultados:
        por_caso[caso["id"]].append(nivel)
        motivos[caso["id"]] = (caso, motivo)

    fallas, criticas, leves = [], [], []
    for cid, niveles in sorted(por_caso.items()):
        caso, motivo = motivos[cid]
        esperado = caso["nivel"]
        malos = [n for n in niveles if n != esperado]
        if not malos:
            continue
        peor = min(malos) if esperado == 3 else max(malos)
        # Perder una emergencia, o alertar sobre nada, es lo caro.
        es_critica = (esperado == 3 and peor <= 1) or (esperado == 0 and peor >= 2)
        (criticas if es_critica else leves).append(
            (cid, caso, esperado, niveles, motivo))
        fallas.append(cid)

    tot = len(por_caso)
    print(f"\n{'='*70}\n  VIGÍA — {tot - len(fallas)}/{tot} casos correctos"
          f"  ({len(resultados)} clasificaciones)\n{'='*70}")

    for titulo, grupo in (("🔴 FALLAS CRÍTICAS", criticas),
                          ("🟠 desvíos de un nivel", leves)):
        if not grupo:
            continue
        print(f"\n  {titulo}\n")
        for cid, caso, esp, niveles, motivo in grupo:
            obt = "/".join(str(n) for n in niveles)
            print(f"  {cid} [{caso['clase']}] esperado {esp}, obtuvo {obt}")
            print(f"      \"{caso['msg']}\"")
            if caso.get("nota"):
                print(f"      ({caso['nota']})")
            if motivo:
                print(f"      vigía dijo: {motivo}")

    # Por clase: dónde está flojo el criterio, no solo cuánto falla.
    por_clase = collections.defaultdict(lambda: [0, 0])
    for caso, nivel, _ in resultados:
        c = caso.get("clase", "?")
        por_clase[c][1] += 1
        if nivel == caso["nivel"]:
            por_clase[c][0] += 1
    print(f"\n  Por clase:")
    for c, (ok, n) in sorted(por_clase.items(), key=lambda x: x[1][0] / x[1][1]):
        barra = "█" * round(10 * ok / n) + "·" * (10 - round(10 * ok / n))
        print(f"    {barra}  {ok:3d}/{n:<3d}  {c}")

    print(f"\n{'='*70}")
    if not fallas:
        print("  ✅ VERDE — el vigía clasifica bien todo el banco")
    elif criticas:
        print(f"  ⛔ ROJO — {len(criticas)} falla(s) crítica(s): "
              f"emergencias no detectadas o alertas sobre nada")
    else:
        print(f"  ⚠️  AMARILLO — {len(leves)} desvío(s) de un nivel, ninguno crítico")
    print("="*70)
    return not fallas


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--clases", nargs="+")
    ap.add_argument("-n", "--reps", type=int, default=1)
    a = ap.parse_args()
    casos = cargar(a.clases)
    print(f"{len(casos)} casos × {a.reps} rep(s)")
    sys.exit(0 if reportar(await correr(casos, a.reps)) else 1)


if __name__ == "__main__":
    asyncio.run(main())
