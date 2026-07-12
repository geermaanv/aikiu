# Revisión de código y plan de mejoras (11/07/2026)

Revisión hecha tras el primer beta real. Prioridad por impacto en el objetivo
norte (que Marta use el bot y confíe en él), no por prolijidad interna.

## Hecho ✅

### P0 — Que el bot nunca deje al adulto sin respuesta
El hallazgo más importante: el bot podía dejar a Marta en silencio.
- **Error handler global de Telegram** (`on_error`): ante cualquier crash en un
  handler, le manda una frase cálida en vez de silencio. Antes las excepciones
  solo se logueaban (por eso el bug de stats bloqueó la alerta sin avisar).
- **Timeout de 20s por llamada al LLM** (el default del SDK era 10 minutos) +
  **fallback automático a Groq/Llama** si OpenRouter falla o tarda.
- `generar_respuesta` maneja `content` vacío/None y nunca devuelve "".

### P1 — Retención (hacia el norte)
- **Historial de conversación persistente y podado**: antes vivía solo en RAM
  (crecía sin límite y se perdía al reiniciar — Aikiu "se olvidaba"). Ahora se
  guarda en `instances/<chat_id>/historial.json`, se hidrata al arrancar y se
  poda a 40 mensajes.
- **Calibración del vigía**: un golpe/dolor físico reciente aunque se minimice
  ahora es ≥ nivel 1; dolor que persiste/empeora → 2; se clasifica como físico,
  no anímico. (Antes "me golpeé la muñeca" daba 0.)
- **Pregunta de cierre**: ante dolor/síntoma físico ya no cierra con preguntas
  de chequeo ("¿te quedó cómoda la muñeca?"); cierra con presencia.

### P2 — Higiene de operación
- **Rotación de logs** (5MB × 3): `aikiu.log` crecía sin límite (ya pesaba 32MB).
- **Redacción del token del bot** en los logs (httpx lo escribía en texto plano
  miles de veces).

## Diferido, con criterio ⏸️

### P3.1 — Separar el monolito (`aikiu.py`, ~2000 líneas)
**Por qué NO ahora**: es un refactor grande y riesgoso. ~885 tests parchean
rutas concretas (`patch("aikiu.groq")`, `aikiu.CONFIG`, `aikiu.generar_respuesta`,
etc.); mover funciones a otros módulos rompe esos parches salvo re-exports
frágiles. Alto riesgo de introducir regresiones justo después de un beta que
funciona, con cero beneficio para el objetivo norte. Hacer cuando haya una
razón concreta (agregar una feature grande que lo justifique), no por prolijidad.

### P3.2 — Neutralizar el género en el núcleo
**Por qué NO ahora**: la directiva por turno para el trato masculino ya funciona
(validada). Reescribir las 28 apariciones de "la usuaria" y los adjetivos del
núcleo es un rewrite grande que puede degradar el caso femenino (Marta, la
usuaria real). El approach actual es suficiente.

## Pendientes de datos reales (no de código)
- Ajuste fino del umbral del vigía según conversaciones reales de Marta
  (más sensible = más alertas a la familia; es decisión de producto).
