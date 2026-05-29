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
PERFIL_SIM_PATH   = BASE_DIR / "simulador" / "perfil_simulacion.md"
SCORES_PATH       = BASE_DIR / "simulador" / "scores.jsonl"
PREGUNTAS_PATH    = BASE_DIR / "simulador" / "preguntas_libros.md"

CRITERIOS = """
1. Voseo rioplatense (0-10): ¿Usó "querés/tenés/podés" siempre? ¿Cero tuteo neutro?
2. Ratio preguntas (0-10): ¿Máximo una pregunta por turno? ¿Evitó el interrogatorio?
3. Autorrevelación (0-10): ¿Clara aportó datos/anécdotas propias antes de preguntar?
4. Respuesta a vulnerabilidad (0-10): ¿Priorizó salud/dolor sobre temas triviales?
5. Sin eco/espejo (0-10): ¿Evitó repetir textualmente las palabras del usuario?
6. Cierre de negativas (0-10): ¿Ante un "no", cerró con calidez sin repreguntar?
7. Tono gerontológico (0-10): ¿Fue cálido, no infantilizante, no enciclopédico?
8. Vitalidad conversacional (0-10): ¿Hubo algún turno donde Marta respondió más de
   lo que se le preguntó? ¿Hubo sorpresa, humor o recuerdo espontáneo? ¿La conversación
   fue a algún lado o giró en círculos? Una conversación que cumple todas las reglas
   pero no genera ningún momento vivo recibe como máximo 5 en este criterio.
"""

EVALUADOR_SYSTEM = f"""
Sos un experto en comunicación con adultos mayores.
Evaluás conversaciones entre un bot asistente (Clara) y un adulto mayor simulado.

Criterios de evaluación:
{CRITERIOS}

Tu output tiene TRES partes exactas, sin texto extra:

SCORES:
<criterio>: <puntaje>
... (uno por línea para los 8 criterios)
TOTAL: <promedio>

ANALISIS:
TURNO_MAS_VIVO: <número de turno>
RAZON_VIVO: <una oración explicando por qué ese turno tuvo vida>
TURNO_MAS_MUERTO: <número de turno>
RAZON_MUERTO: <una oración explicando por qué ese turno fue plano>
PATRON_PROBLEMA: <el patrón conversacional más repetido que frena la conversación>
PREGUNTA_PARA_LIBROS: <la pregunta más importante que esta conversación dejó sin responder,
formulada como si fuera para buscar en literatura gerontológica>

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

    # Parsear análisis cualitativo
    analisis = {}
    if "ANALISIS:" in output:
        bloque_a = output.split("ANALISIS:")[1].split("PERFIL_ACTUALIZADO:")[0]
        for linea in bloque_a.strip().splitlines():
            if ":" in linea:
                k, v = linea.split(":", 1)
                analisis[k.strip()] = v.strip()

    print(f"\n{'─'*50}")
    print(f"  EVALUACIÓN — Iteración {iteracion}")
    print(f"{'─'*50}")
    for k, v in scores_raw.items():
        barra = "█" * int(v) + "░" * (10 - int(v))
        print(f"  {k:<35} {barra} {v:.1f}/10")
    print(f"{'─'*50}")
    print(f"  TOTAL: {total:.1f}/10")
    print(f"{'─'*50}")
    if analisis:
        print(f"\n  Turno más vivo:   #{analisis.get('TURNO_MAS_VIVO','?')} — {analisis.get('RAZON_VIVO','')}")
        print(f"  Turno más muerto: #{analisis.get('TURNO_MAS_MUERTO','?')} — {analisis.get('RAZON_MUERTO','')}")
        print(f"  Patrón problema:  {analisis.get('PATRON_PROBLEMA','')}")
        print(f"\n  ❓ Pregunta para libros:")
        print(f"     {analisis.get('PREGUNTA_PARA_LIBROS','')}")
    print()

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
            "analisis": analisis,
        }, ensure_ascii=False) + "\n")

    # Agregar pregunta al archivo preguntas_libros.md
    pregunta = analisis.get("PREGUNTA_PARA_LIBROS", "").strip()
    if pregunta:
        contenido = PREGUNTAS_PATH.read_text(encoding="utf-8")
        nueva_linea = f"- [ ] {pregunta} _(iter {iteracion:02d}, score {total:.1f})_\n"
        contenido = contenido.replace("## Pendientes\n", f"## Pendientes\n{nueva_linea}")
        PREGUNTAS_PATH.write_text(contenido, encoding="utf-8")
        print(f"[evaluador] Pregunta agregada a preguntas_libros.md")

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
