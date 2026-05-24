#!/bin/bash
# Atajo para configurar.py. Sin argumentos regenera el template
# neutro (perfil.md + config.yml de la raíz). Para configurar un
# hogar existente, pasá --chat-id <id>.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$DIR/venv" ]; then
    echo "  Primero corré: bash setup.sh"
    exit 1
fi

"$DIR/venv/bin/python" "$DIR/configurar.py" "$@"
