#!/usr/bin/env bash
# Lanza los 3 bots de Aikiu en un solo contenedor de Railway:
#   - aikiu.py        (siempre, bot del adulto mayor)
#   - familiar_bot.py (si FAMILIAR_BOT_TOKEN está seteado)
#   - admin/bot.py    (si ADMIN_BOT_TOKEN está seteado)
#
# A diferencia de start.sh (pensado para dev local con .env y venv), este
# script lee directo de las env vars que Railway inyecta y usa el python del
# sistema (el que NIXPACKS deja en PATH).
#
# Política de fallo: esperamos al primer proceso que muera y salimos con su
# exit code. Railway aplica la restartPolicy de railway.json y reinicia el
# contenedor entero (más simple y robusto que intentar reiniciar bots sueltos
# desde acá).

set -u
cd "$(dirname "$0")"

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[railway_start] Lanzando aikiu (bot principal)..."
python -u aikiu.py &
PIDS+=($!)

if [ -n "${FAMILIAR_BOT_TOKEN:-}" ]; then
  echo "[railway_start] Lanzando familiar_bot..."
  python -u familiar_bot.py &
  PIDS+=($!)
else
  echo "[railway_start] FAMILIAR_BOT_TOKEN ausente — skip familiar_bot"
fi

if [ -n "${ADMIN_BOT_TOKEN:-}" ]; then
  echo "[railway_start] Lanzando admin/bot.py..."
  python -u admin/bot.py &
  PIDS+=($!)
else
  echo "[railway_start] ADMIN_BOT_TOKEN ausente — skip admin/bot.py"
fi

# Esperamos al primero que muera; salimos con su exit code para que Railway
# reinicie el contenedor entero (restartPolicy: ON_FAILURE en railway.json).
wait -n
EXIT_CODE=$?
echo "[railway_start] Un proceso terminó con código $EXIT_CODE — bajando el resto..."
exit "$EXIT_CODE"
