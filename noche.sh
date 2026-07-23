#!/usr/bin/env bash
# Trabajo nocturno de MEDICIÓN — junta evidencia mientras dormís.
#
#   caffeinate -is nohup bash noche.sh > /dev/null 2>&1 &
#
# Corre solo, sin Claude: es Python llamando a las APIs (OpenRouter/Groq), no
# consume tokens de la sesión. A la mañana hay un informe con números honestos
# sobre los que arreglar con datos, en vez de a ciegas.
#
# NO TOCA CÓDIGO NI REGLAS. Eso necesita criterio humano — un script que
# reescriba reglas solo es exactamente lo que memory/learning.md #8 desaconseja.
# Solo mide y guarda.
#
# Resiliente al rate limit: si Groq/OpenRouter devuelven 429, espera y reintenta.
# La cuota diaria de Groq se resetea, así que varias pasadas a lo largo de la
# noche capturan las ventanas en que hay crédito.
set -uo pipefail
cd "$(dirname "$0")"
PY="./venv/bin/python"
STAMP="$(date +%Y%m%d_%H%M%S)"
INFORME="noche_${STAMP}.md"
LOG="logs/noche_${STAMP}.log"
mkdir -p logs

filtro() { grep -aviE 'HTTP Request|Hot-reload|OpenRouter falló|Warning|it/s|Pre-route|Receptividad'; }

titulo() {
  echo -e "\n\n## $1  ($(date +%H:%M))\n" >> "$INFORME"
  echo "════════ $1 ($(date +%H:%M)) ════════" >> "$LOG"
}

# Bloque de resumen que puedo leer rápido a la mañana.
veredicto() {  # extrae la parte del reporte que importa
  awk '/VEREDICTO|Aserciones que fallan|✗|🔴|🟢|✅|⛔|Por clase/{p=1} p' | head -60
}

cat > "$INFORME" <<EOF
# Informe nocturno — $STAMP

Medición automática, sin cambios de código. Para revisar a la mañana con
tokens y decidir qué arreglar. Cada bloque es un número honesto: nada acá se
declaró "arreglado" con una prueba manual (ver memory/learning.md #1).

Orden de lectura sugerido: mirar primero los VEREDICTOS, después el detalle.
EOF

# ── 1. La base de todo: los tests deben pasar antes de medir nada ───────────
titulo "pytest (línea de base)"
if $PY -m pytest tests/ -q >> "$LOG" 2>&1; then
  echo "✓ pytest en verde — la medición es confiable" >> "$INFORME"
else
  echo "⚠️ pytest ROJO — algo se rompió, revisar antes que nada:" >> "$INFORME"
  tail -15 "$LOG" | grep -E 'FAILED|Error' >> "$INFORME"
fi

# ── 2. Banco del vigía — barato y es lo más caro que puede fallar ───────────
titulo "Banco del vigía (clasificación de riesgo)"
$PY simulador/correr_vigia.py >> "$LOG" 2>&1
tail -80 "$LOG" | veredicto >> "$INFORME"

# ── 3. Gate por nivel, con muestra grande. n=8 para números confiables ──────
# Se corre cada nivel dos veces a lo largo de la noche: si una falla aparece en
# una pasada y no en la otra, es intermitente y hay que saberlo.
for pasada in 1 2; do
  for nivel in 1 2 3; do
    titulo "Gate nivel $nivel — pasada $pasada (n=8)"
    if $PY simulador/ciclo.py -l "$nivel" -n 8 >> "$LOG" 2>&1; then
      tail -90 "$LOG" | veredicto >> "$INFORME"
    else
      # Probablemente rate limit. Esperar 20 min y seguir con el próximo.
      echo "(no completó — probable rate limit; se retoma en la próxima pasada)" >> "$INFORME"
      sleep 1200
    fi
  done
done

# ── 4. Crecer el banco de casos desde los libros (si queda crédito) ─────────
titulo "Extracción de casos del vigía desde los libros"
$PY kb/extraer_casos_vigia.py --muestra 60 >> "$LOG" 2>&1 \
  && echo "✓ casos nuevos en simulador/casos_vigia_revisar.jsonl (revisar a mano)" >> "$INFORME" \
  || echo "(no completó — sin crédito o error; se puede reintentar de día)" >> "$INFORME"

# ── Cierre ──────────────────────────────────────────────────────────────────
titulo "Resumen"
cat >> "$INFORME" <<EOF

Terminó $(date +%H:%M).

**Para la mañana:**
1. Leer los VEREDICTOS de arriba. Las fallas que aparecen en las DOS pasadas
   son las firmes; las que aparecen en una sola son intermitentes.
2. Antes de arreglar cada una: ¿es de Aikiu o del medidor? (9 de 22 del 22/07
   eran del medidor).
3. Correr \`bash spec.sh <tema>\` antes de tocar la regla.
4. Log completo en $LOG.
EOF

echo "LISTO $(date)" >> "$LOG"
