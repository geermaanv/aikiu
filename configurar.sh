#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$DIR/venv" ]; then
    echo "  Primero corré: bash setup.sh"
    exit 1
fi

"$DIR/venv/bin/python" "$DIR/configurar.py"
