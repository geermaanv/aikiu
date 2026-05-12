#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Verificar credenciales principales (solo las obligatorias)
env_val() { grep "^$1=" "$DIR/.env" 2>/dev/null | cut -d= -f2-; }

for var in BOT_TOKEN CHAT_ID GROQ_API_KEY; do
    val=$(env_val "$var")
    if [ -z "$val" ] || echo "$val" | grep -q "PEGA_TU"; then
        echo "  ERROR: Completá $var en .env"
        echo "  open -e .env"
        exit 1
    fi
done

echo ""
echo "  Aikiu iniciando..."
echo "  Ctrl+C para detener."
echo ""

PIDS=""

"$DIR/venv/bin/python" aikiu.py &
PIDS="$!"

# Bot familiar (opcional — configurar FAMILIAR_BOT_TOKEN y FAMILIAR_CHAT_ID en .env)
familiar_token=$(env_val "FAMILIAR_BOT_TOKEN")
if [ -n "$familiar_token" ] && ! echo "$familiar_token" | grep -q "PEGA_TU"; then
    "$DIR/venv/bin/python" familiar_bot.py &
    PIDS="$PIDS $!"
    echo "  Bot familiar activo."
fi

cleanup() { kill $PIDS 2>/dev/null; }
trap cleanup SIGINT SIGTERM

wait
