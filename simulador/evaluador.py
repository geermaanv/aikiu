"""
Evaluador de simulaciones Aikiu.
Lee la conversación, puntúa, y actualiza perfil_simulacion.md (nunca perfil.md).
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
import os

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
PERFIL_SIM_PATH = BASE_DIR / "simulador" / "perfil_simulacion.md"
SCORES_PATH     = BASE_DIR / "simulador" / "scores.jsonl"

CRITERIOS = """
1. Voseo rioplatense (0-10): ¿Usó "querés/tenés/podés" siempre? ¿Cero tuteo neutro?
2. Ratio preguntas (0-10): ¿Máximo una pregunta por turno? ¿Evitó el interrogatorio?
3. Autorrevelación (0-10): ¿Clara aportó datos/anécdotas propias antes de preguntar?
4. Respuesta a vulnerabilidad (0-10): ¿Priorizó salud/dolor sobre temas triviales?
5. Sin eco/espejo (0-10): ¿Evitó repetir textualmente las palabras del usuario?
6. Cierre de negativas (0-10): ¿Ante un "no", cerró con calidez sin repreguntar?
7. Tono gerontológico (0-10): ¿Fue cálido, no infantilizante, no enciclopédico?
"""

EVALUADOR_SYSTEM = f"""
Sos un experto en comunicación con adultos mayores.
Evaluás conversaciones entre un bot asistente (Clara) y un adulto mayor simulado.

Criterios de evaluación:
{CRITERIOS}

Tu output tiene DOS partes exactas, sin texto extra:

SCORES:
<criterio>: <puntaje>
... (uno por línea para los 7 criterios)
TOTAL: <promedio>

PERFIL_ACTUALIZADO:
<el perfil.md completo actualizado en markdown, solo las secciones "Cómo hablarle",
"Iniciativa conversacional" y "Temas a manejar con cuidado" pueden cambiar.
El resto del perfil debe quedar IDÉNTICO al original.>
"""


def puntuar_y_actualizar(log_path: Path, iteracion: int = 1) -> float:
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY en .env")

    with open(log_path, encoding="utf-8") as f:
        conversacion = [json.loads(l) for l in f]

    perfil_actual = PERFIL_SIM_PATH.read_text(encoding="utf-8")

    prompt = f"""
## Perfil actual del bot (perfil_simulacion.md):
{perfil_actual}

## Conversación simulada ({len(conversacion)} turnos):
{json.dumps(conversacion, ensure_ascii=False, indent=2)}

Evaluá y devolvé exactamente el formato pedido.
"""

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    resp = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"system_instruction": EVALUADOR_SYSTEM},
    )
    output = resp.text.strip()

    # Parsear scores
    scores_raw = {}
    total = 0.0
    if "SCORES:" in output:
        bloque = output.split("SCORES:")[1].split("PERFIL_ACTUALIZADO:")[0]
        for linea in bloque.strip().splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                k = k.strip()
                try:
                    val = float(v.strip().split("/")[0])
                    if k.upper() == "TOTAL":
                        total = val
                    else:
                        scores_raw[k] = val
                except ValueError:
                    pass

    print(f"\n{'─'*50}")
    print(f"  EVALUACIÓN — Iteración {iteracion}")
    print(f"{'─'*50}")
    for k, v in scores_raw.items():
        barra = "█" * int(v) + "░" * (10 - int(v))
        print(f"  {k:<35} {barra} {v:.1f}/10")
    print(f"{'─'*50}")
    print(f"  TOTAL: {total:.1f}/10")
    print(f"{'─'*50}\n")

    # Leer score anterior
    score_anterior = 0.0
    if SCORES_PATH.exists():
        lineas = SCORES_PATH.read_text(encoding="utf-8").strip().splitlines()
        if lineas:
            try:
                score_anterior = json.loads(lineas[-1]).get("total", 0.0)
            except Exception:
                pass

    # Guardar score
    with open(SCORES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "iteracion": iteracion,
            "ts": datetime.utcnow().isoformat(),
            "scores": scores_raw,
            "total": total,
            "log": log_path.name,
        }, ensure_ascii=False) + "\n")

    # Solo actualizar perfil si mejoró
    if total > score_anterior and "PERFIL_ACTUALIZADO:" in output:
        nuevo_perfil = output.split("PERFIL_ACTUALIZADO:")[1].strip()
        # Limpiar posibles bloques de código
        if nuevo_perfil.startswith("```"):
            nuevo_perfil = "\n".join(nuevo_perfil.splitlines()[1:])
        if nuevo_perfil.endswith("```"):
            nuevo_perfil = "\n".join(nuevo_perfil.splitlines()[:-1])

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy(PERFIL_SIM_PATH, PERFIL_SIM_PATH.parent / f"perfil_sim_backup_{ts}.md")
        PERFIL_SIM_PATH.write_text(nuevo_perfil.strip() + "\n", encoding="utf-8")
        print(f"[evaluador] ✓ perfil_simulacion.md actualizado (score {score_anterior:.1f} → {total:.1f})")
    else:
        print(f"[evaluador] ✗ No se actualizó (score {total:.1f} ≤ anterior {score_anterior:.1f})")

    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Tomar el log más reciente
        logs = sorted(Path(BASE_DIR / "simulador" / "logs").glob("*.jsonl"))
        if not logs:
            print("No hay logs. Corré simulador.py primero.")
            sys.exit(1)
        log_path = logs[-1]
    else:
        log_path = Path(sys.argv[1])
    puntuar_y_actualizar(log_path)
