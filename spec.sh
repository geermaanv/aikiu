#!/usr/bin/env bash
# Arranca la especificación de un cambio de comportamiento (ver CAMBIOS.md).
#
#   bash spec.sh soledad
#   bash spec.sh "largo|oraciones"
#
# Automatiza los dos campos que más retrabajo causaron el 22/07: "qué dice el
# sistema hoy" (se agregó una regla de largo afirmando que no existía, y había
# una contradictoria en otra sección) y "con qué choca" (dos bugs salieron de
# reglas que se pisaban sin precedencia declarada). Un grep cuesta diez
# segundos; descubrirlo después cuesta una tarde.
set -uo pipefail
cd "$(dirname "$0")"

[ $# -eq 0 ] && { echo "uso: bash spec.sh <tema>   (ej: soledad, largo, fallecido)"; exit 1; }
TEMA="$1"

echo "════════════════════════════════════════════════════════════════"
echo "  ESPECIFICACIÓN DE CAMBIO — tema: $TEMA"
echo "════════════════════════════════════════════════════════════════"

echo
echo "▸ 2. QUÉ DICE EL SISTEMA HOY"
echo "  ── aikiu_core.md ──"
grep -in "$TEMA" aikiu_core.md | head -20 | sed 's/^/    /' || echo "    (nada)"
echo "  ── prompt del vigía / código ──"
grep -in "$TEMA" aikiu.py | grep -viE '^\s*[0-9]+:\s*#' | head -8 | sed 's/^/    /' || echo "    (nada)"

echo
echo "▸ 3. SECCIONES QUE TOCAN EL MISMO TERRENO (¿con cuál choca?)"
./venv/bin/python - "$TEMA" <<'PY'
import re, sys
tema = sys.argv[1].lower()
txt = open("aikiu_core.md").read()
bloques = re.split(r"^## ", txt, flags=re.M)[1:]
for b in bloques:
    titulo = b.split("\n")[0]
    if re.search(tema, b, re.I):
        n = len(re.findall(tema, b, re.I))
        print(f"    · {titulo}  ({n} menciones)")
PY

echo
echo "▸ 4. VERIFICACIÓN — aserciones que ya cubren esto"
./venv/bin/python - "$TEMA" <<'PY'
import json, re, sys
tema = sys.argv[1].lower()
d = json.load(open("simulador/aserciones.json"))
hay = False
for a in d["globales"]:
    if re.search(tema, json.dumps(a, ensure_ascii=False), re.I):
        print(f"    · {a['id']} (global): {a['falla'][:78]}")
        hay = True
for esc, grupo in d["por_escenario"].items():
    for a in grupo:
        if re.search(tema, json.dumps(a, ensure_ascii=False), re.I) or tema in esc:
            print(f"    · {a['id']} (escenario '{esc}'): {a['falla'][:66]}")
            hay = True
if not hay:
    print("    ⚠️  NINGUNA. Si cambiás esto, no hay forma binaria de saber si quedó bien.")
    print("       Escribí la aserción ANTES del cambio (ver CAMBIOS.md).")
PY

echo
echo "▸ COMANDOS DE VERIFICACIÓN"
./venv/bin/python - "$TEMA" <<'PY'
import json, sys
tema = sys.argv[1].lower()
esc = json.load(open("simulador/escenarios.json"))
cand = [k for k in esc if not k.startswith("_") and (tema in k or k in tema)]
if cand:
    for c in cand:
        print(f"    ./venv/bin/python simulador/ciclo.py -e {c} -n 8      # ~8 min")
else:
    print(f"    (ningún escenario se llama '{tema}' — elegí uno:)")
    print("    " + "  ".join(k for k in esc if not k.startswith("_")))
print("    ./venv/bin/python simulador/correr_vigia.py           # ~3 min, si tocás riesgo")
print("    ./venv/bin/python -m pytest tests/ -q                 # siempre")
PY

echo
echo "  Recordá el campo 4: una falla del 5% necesita ~50 corridas para verse."
echo "  Un verde con 16 no es verde (pasó el 22/07)."
echo "════════════════════════════════════════════════════════════════"
