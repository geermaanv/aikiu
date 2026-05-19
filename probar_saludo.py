"""
Script de prueba rápida para el saludo matutino con temperatura.
Envía el saludo a Marta ahora mismo, sin esperar al scheduler.

Uso:
    source venv/bin/activate
    python probar_saludo.py
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

async def main():
    # Importar después de cargar .env
    from aikiu import CONFIG, saludo_matutino
    from telegram import Bot

    print(f"Ciudad configurada: {CONFIG.get('ciudad', 'Buenos Aires')}")
    print(f"Enviando saludo a {CONFIG['nombre_adulto_mayor']}...")

    class FakeApp:
        bot = Bot(token=CONFIG["bot_token"])

    await saludo_matutino(FakeApp())
    print("✓ Saludo enviado. Revisá el chat de Marta.")

if __name__ == "__main__":
    asyncio.run(main())
