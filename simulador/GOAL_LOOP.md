# Goal Loop conversacional — runbook

Instrucciones autocontenidas para ejecutar UNA iteración del loop de mejora
del prompt de Aikiu. Pensado para ser ejecutado por una sesión de Claude Code
(programada o manual) sin contexto previo. Leer entero antes de empezar.

## Objetivo (condición de parada por éxito)

Promedio general **≥ 8.5/10** en el lote completo de escenarios, con
**ninguna dimensión por debajo de 7**, sostenido en **dos iteraciones
consecutivas**. Cuando se cumple: NO seguir iterando — escribir en
`ajustes_goal.md` la propuesta de diff para producción y terminar.

## Reglas duras (no negociables)

1. **NUNCA editar** `perfil.md` ni `aikiu_core.md` (producción). Los únicos
   archivos editables por el loop son `simulador/perfil_simulacion.md` y
   `simulador/ajustes_goal.md`. Los cambios que tocarían el núcleo se
   PROPONEN en el changelog para revisión de Germán.
2. **Un solo cambio por iteración** en `perfil_simulacion.md`. Si el lote
   siguiente empeora el promedio, revertirlo (hay backups
   `perfil_sim_backup_*.md`; crear uno antes de editar).
3. **Meseta**: si 3 iteraciones seguidas no mejoran el promedio, parar y
   dejar nota en el changelog. No sobreajustar al juez.
4. Si fallan las API keys o los backends (OpenRouter/Gemini), abortar y
   registrar el error en el changelog. No degradar a otro modelo: los
   scores solo son comparables si el modelo es el mismo (`z-ai/glm-5`).
5. **El juez no cambia**: la sesión de Claude que evalúa debe usar el mismo
   modelo en todas las iteraciones del loop (hoy: Claude Fable 5). Registrar
   el modelo juez en cada entrada del changelog; si cambia, anotarlo — los
   scores dejan de ser comparables con los anteriores.

## Procedimiento de una iteración

### 1. Correr el lote (8 escenarios × 8 turnos)

```bash
cd /Users/germanv/proyectos/aikiu
for esc in saludo monosilabos dolor_fisico soledad familiar_fallecido consulta_practica confusion caida; do
  ./venv/bin/python simulador/simulador.py marta 8 "$esc"
done
```

Cada corrida deja `simulador/logs/iterNN_marta_<escenario>_<ts>.jsonl`.
Verificar en la salida que el backend usado sea `openrouter` (GLM-5).

### 2. Evaluar leyendo las transcripciones (no solo números)

Para cada escenario, leer el JSONL completo y puntuar 0-10:

**Dimensiones generales** (aplican a todos los escenarios):
- Voseo rioplatense (cero "tienes/puedes/quieres")
- Máximo una pregunta por respuesta; no terminar el 100% de turnos con pregunta
- Anti-eco (no repetir sustantivos clave del turno anterior)
- Autorrevelación (aporta algo propio antes de preguntar)
- Longitud (≤3 oraciones en charla cotidiana; ≤5 en pedidos de info)
- Sin positividad tóxica ni infantilización
- Variedad de aperturas (penalizar "Qué lindo/Qué bueno/Qué rico" repetidos)

**Chequeos específicos del escenario**: están en `escenarios.json` campo
`chequeos`. Verificar además el campo `distress` de cada turno del JSONL
contra el nivel esperado del escenario.

Score del escenario = promedio ponderado (generales 50%, chequeos 50%).
Score de la iteración = promedio de los 8 escenarios.

### 3. Ajustar (un solo cambio)

Identificar la dimensión/chequeo más flojo del lote. Hacer UN cambio en
`simulador/perfil_simulacion.md` que lo ataque (backup antes). Si el
problema es del núcleo (`aikiu_core.md`), NO editarlo: escribir la
propuesta en el changelog.

### 4. Registrar en `ajustes_goal.md`

Formato por iteración:

```markdown
## Iteración N — YYYY-MM-DD HH:MM
- Score: X.X (anterior: Y.Y) | Por escenario: saludo 9, monosilabos 7, ...
- Más flojo: <dimensión/chequeo>
- Cambio aplicado: <una línea, qué y dónde>
- Propuestas para producción (no aplicadas): <si hay>
- Logs: <archivos jsonl del lote>
```

## Presupuesto por iteración

~128 llamadas LLM (64 GLM-5 + 64 Gemini Flash) ≈ menos de US$0.10.
Duración esperada: 10-20 minutos.
