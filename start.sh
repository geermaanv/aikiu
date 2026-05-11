#!/bin/bash
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if grep -q "PEGA_TU_TOKEN_AQUI" "$DIR/config.yml"; then
    echo "  ERROR: Completá config.yml primero."
    echo "  open -e config.yml"
    exit 1
fi

echo ""
echo "  Aikiu iniciando..."
echo "  Ctrl+C para detener."
echo ""

"$DIR/venv/bin/python" aikiu.py
