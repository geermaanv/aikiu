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

# Verificar config
if grep -q "PEGA_TU_TOKEN_AQUI" "$DIR/config.yml"; then
    echo ""
    echo "  Completá config.yml antes de iniciar:"
    echo "  open -e config.yml"
    echo ""
    echo "  Necesitás:"
    echo "  - bot_token    → @BotFather en Telegram"
    echo "  - chat_id      → del celular del anciano"
    echo "  - groq_api_key → console.groq.com (gratis)"
    echo ""
else
    echo ""
    ok "config.yml configurado"
    echo -e "${GREEN}  Iniciá con: bash start.sh${RESET}"
    echo ""
fi
