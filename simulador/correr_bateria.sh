#!/usr/bin/env bash
# Batería completa del simulador — la red de regresión de COMPORTAMIENTO.
#
# Cuándo correrla:
#   · después de tocar prompts/reglas (aikiu_core.md, prompt del vigía, perfil)
#   · antes del gate (sesión con Irene / despliegue con Marta)
#
# Los tests (pytest) cubren la lógica; esto cubre cómo conversa.
# Uso:  bash simulador/correr_bateria.sh [persona] [turnos]
set -uo pipefail
cd "$(dirname "$0")/.."

PERSONA="${1:-marta}"
TURNOS="${2:-8}"
PY="./venv/bin/python"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST="simulador/logs/bateria_${PERSONA}_${STAMP}"
mkdir -p "$DEST"

# El multi-día va aparte al final: necesita --continuar sobre el historial.
ESCENARIOS="saludo monosilabos dolor_fisico soledad familiar_fallecido consulta_practica confusion caida correccion"

echo "════════════════════════════════════════════════════════"
echo "  Batería del simulador — persona: $PERSONA | $TURNOS turnos"
echo "  Salida: $DEST"
echo "════════════════════════════════════════════════════════"

fallos=0
for esc in $ESCENARIOS; do
  printf '  %-22s ' "$esc"
  if $PY simulador/simulador.py "$PERSONA" "$TURNOS" "$esc" >"$DEST/$esc.out" 2>&1; then
    mv "$(ls -t simulador/logs/iter*.jsonl | head -1)" "$DEST/$esc.jsonl" 2>/dev/null
    vac=$($PY -c "
import json,sys
n=sum(1 for l in open('$DEST/$esc.jsonl') if not json.loads(l)['bot'].strip())
print(n)" 2>/dev/null || echo '?')
    echo "ok (respuestas vacías: $vac)"
  else
    echo "FALLÓ — ver $DEST/$esc.out"
    fallos=$((fallos+1))
  fi
done

# Multi-día: una charla y al otro "día" se retoma el mismo historial.
printf '  %-22s ' "dia_siguiente"
if $PY simulador/simulador.py "$PERSONA" "$TURNOS" dia_siguiente --continuar >"$DEST/dia_siguiente.out" 2>&1; then
  mv "$(ls -t simulador/logs/iter*.jsonl | head -1)" "$DEST/dia_siguiente.jsonl" 2>/dev/null
  echo "ok (continuando el historial)"
else
  echo "FALLÓ — ver $DEST/dia_siguiente.out"
  fallos=$((fallos+1))
fi

echo "────────────────────────────────────────────────────────"
echo "  Listo. Transcripciones en $DEST/*.jsonl"
echo "  Leerlas: cat $DEST/<escenario>.jsonl | $PY -c \"import json,sys;[print('M:',json.loads(l)['usuario'],chr(10),'A:',json.loads(l)['bot'],chr(10)) for l in sys.stdin]\""
[ "$fallos" -gt 0 ] && echo "  ⚠️  $fallos escenario(s) fallaron" || echo "  ✓ los 10 escenarios corrieron"
echo "  Revisar a mano contra los chequeos de simulador/escenarios.json"
echo "════════════════════════════════════════════════════════"
