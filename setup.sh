#!/bin/bash
# setup.sh — Instala Aikiu en Mac (versión Groq, sin Ollama ni Whisper local)

set -e
GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RESET="\033[0m"
ok()  { echo -e "${GREEN}  ✓ $1${RESET}"; }
inf() { echo -e "${YELLOW}  → $1${RESET}"; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo "  Aikiu — Setup"
echo ""

# Python
inf "Verificando Python..."
PYTHON=$(command -v python3.11 || command -v python3)
ok "Python: $($PYTHON --version)"

# Entorno virtual
inf "Configurando entorno Python..."
if [ ! -d "$DIR/venv" ]; then
    $PYTHON -m venv "$DIR/venv"
fi
"$DIR/venv/bin/pip" install -q --upgrade pip
"$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
ok "Dependencias instaladas"

# Verificar .env
if [ ! -f "$DIR/.env" ]; then
    cp "$DIR/.env.example" "$DIR/.env"
fi

if grep -q "PEGA_TU" "$DIR/.env"; then
    echo ""
    echo "  Completá .env antes de iniciar:"
    echo "  open -e .env"
    echo ""
    echo "  Necesitás:"
    echo "  - BOT_TOKEN    → @BotFather en Telegram"
    echo "  - CHAT_ID      → del celular del anciano"
    echo "  - GROQ_API_KEY → console.groq.com (gratis)"
    echo ""
else
    echo ""
    ok ".env configurado"
    echo -e "${GREEN}  Iniciá con: bash start.sh${RESET}"
    echo ""
fi
