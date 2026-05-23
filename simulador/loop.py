"""
Loop completo: N iteraciones de simulación + evaluación.
Escribe solo en perfil_simulacion.md, nunca en perfil.md.

Uso:
  python simulador/loop.py                    # 3 iteraciones, persona marta, 10 turnos
  python simulador/loop.py 5                  # 5 iteraciones
  python simulador/loop.py 3 marta 8          # 3 iter, persona marta, 8 turnos
"""

import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from simulador.simulador import simular
from simulador.evaluador import puntuar_y_actualizar

ITERACIONES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
PERSONA     = sys.argv[2] if len(sys.argv) > 2 else "marta"
TURNOS      = int(sys.argv[3]) if len(sys.argv) > 3 else 10


async def main():
    print(f"\n{'#'*60}")
    print(f"  LOOP SIMULADOR AIKIU")
    print(f"  Iteraciones: {ITERACIONES} | Persona: {PERSONA} | Turnos: {TURNOS}")
    print(f"{'#'*60}")

    for i in range(1, ITERACIONES + 1):
        conversacion, log_path = await simular(
            persona=PERSONA,
            turnos=TURNOS,
            iteracion=i,
        )
        puntuar_y_actualizar(log_path, iteracion=i)

    print(f"\n{'#'*60}")
    print(f"  Loop completo.")
    print(f"  perfil_simulacion.md contiene la versión final.")
    print(f"  Revisá simulador/logs/ para ver las conversaciones.")
    print(f"  Revisá simulador/scores.jsonl para ver la evolución.")
    print(f"{'#'*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
