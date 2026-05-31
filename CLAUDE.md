# Documentación al día en cada push

Antes de ejecutar `git push` (o cuando el usuario pida "push"), revisá si los cambios incluidos en los commits a empujar afectan la documentación. Si afectan, actualizá la docu en el mismo push (commit adicional o amend si corresponde) antes de empujar.

## Qué revisar

Mirá `git log origin/<branch>..HEAD` (o `git diff origin/<branch>..HEAD --stat`) y chequeá si los cambios tocan:

| Si cambió... | Actualizá... |
|---|---|
| Comandos de bot, flujos de usuario, capacidades | `README.md` |
| Variables de entorno nuevas o renombradas | `.env.example` **y** `README.md` (sección de configuración) |
| Estructura del repo (archivos/carpetas nuevos relevantes) | `README.md` (sección "Estructura") |
| Scripts de arranque (`start.sh`, `configurar.py`) | `README.md` (sección "Cómo correr") |
| Funcionalidad planeada que ya quedó hecha | `ROADMAP.md` |
| Endpoints/APIs públicas | `README.md` + docs específicas si existen |

## Procedimiento

1. **Antes** de `git push`, listá los archivos modificados desde la última vez que la rama está sincronizada con origin.
2. Decidí si alguna docu queda desactualizada. Si dudás, preguntá al usuario antes de empujar.
3. Si hay que actualizar: hacelo, agregá al commit pertinente (nuevo commit o amend si el commit es local y reciente, respetando las reglas de amend) y recién ahí pusheá.
4. Si todo está al día, pusheá y mencionalo brevemente ("docu revisada, sin cambios necesarios").

## Qué NO hacer

- No inventes secciones de docu nuevas sin necesidad.
- No agregues badges, screenshots o tablas decorativas no pedidas.
- No toques `ROADMAP.md` para tachar items que el usuario no confirmó como completados.

---

# Cambios en modelos LLM — actualizar todo el repo

Esta regla aplica **solo si tu cambio agrega, renombra, reemplaza o quita un modelo de LLM** (chat o audio). Si no estás tocando modelos, ignorala.

## Cuándo dispararla

Activá esta checklist cuando aparezca cualquiera de estas señales en lo que vas a editar:

- Una llamada a Groq con `model="..."` con un valor nuevo o distinto al `llama-3.3-70b-versatile` / `whisper-large-v3` actuales.
- Una nueva entrada `modelo_llm:` en `config.yml`, o un `ANDROMARTA_MODELO=...` distinto.
- Un test que registra uso con `registrar_chat("modelo-nuevo", ...)` o `timed_chat("modelo-nuevo")`.
- El usuario te pide explícitamente "cambiar de modelo", "probar un modelo nuevo", "usar X en lugar de Y".

## Touchpoints a actualizar (en este orden)

| # | Archivo | Qué chequear |
|---|---|---|
| 1 | `core/llm_limits.py` | Agregar / actualizar la entrada del modelo en el dict `FREE_TIER` con sus 4 ejes (RPM, RPD, TPM, TPD para chat; RPM, RPD, ASH, ASD para audio). Si no figura en la doc oficial de Groq, dejá None y comentalo. Fuente canónica: https://console.groq.com/docs/rate-limits |
| 2 | `config.yml` | Si el modelo va a ser el default de Aikiu, actualizá `modelo_llm:`. Si convive con otros, dejá el actual y documentá la elección en el commit. |
| 3 | `aikiu.py` | Los `CONFIG.get("modelo_llm", "...")` tienen un fallback hardcodeado: si cambia el default, actualizalo en TODAS las ocurrencias (hoy son 4). |
| 4 | `andromarta/bot.py` | El default de `MODELO = os.environ.get("ANDROMARTA_MODELO", "...")` también está hardcodeado. |
| 5 | `andromarta/.env.example` | Línea `ANDROMARTA_MODELO=...`. |
| 6 | `.env.example` | El comentario de `GROQ_DAILY_TOKEN_LIMIT` menciona explícitamente el modelo de referencia con sus límites — actualizalo si el default cambió. |
| 7 | `README.md` | Sección "Configuración" (variables de entorno) y la tabla técnica donde dice `Groq llama-3.3-70b-versatile`. También el diagrama Mermaid si lo menciona. |
| 8 | `admin/COMO_USAR.md` | Sección de troubleshooting de los 429 — incluye los 4 ejes del modelo de referencia. |
| 9 | `tests/test_usage.py`, `tests/test_analisis_nocturno.py` | Fixtures que hardcodean el nombre del modelo (busca `"llama-3.3-70b-versatile"` y `"whisper-large-v3"`). Si el cambio es agregar un modelo NUEVO sin reemplazar, los tests viejos pueden seguir igual; si reemplazás, actualizá. |

## Cómo ejecutar la checklist

1. **Antes de aplicar cualquier cambio que cumpla las condiciones de arriba**: tomá nota del nombre exacto del modelo (con su slug completo, ej. `meta-llama/llama-4-scout-17b-16e-instruct`).
2. Recorré los 9 touchpoints en orden. Si un archivo no menciona el modelo, no lo toques.
3. Para `core/llm_limits.py`: si no encontrás los límites en la doc oficial de Groq, **preguntale al usuario** antes de inventar valores — la tabla se usa para los avisos de cuota del admin bot y un valor inventado puede dar señales falsas.
4. Después de los cambios, ejecutá los tests relacionados:
   ```
   .\venv\Scripts\python.exe -m pytest tests/test_usage.py tests/test_admin_state.py -q
   ```
5. Si el bot admin está corriendo, reinicialo (mata el proceso de `admin\bot.py` y volvelo a lanzar) para que el `/llm` levante el catálogo actualizado.

## Qué NO hacer

- **No agregues modelos al catálogo "por las dudas"**. Solo agregá los que realmente se vayan a usar; si no, el catálogo se vuelve ruido.
- **No edites el catálogo sin verificar contra la doc oficial de Groq.** Los límites cambian seguido y los datos viejos engañan.
- **No borres una entrada del catálogo** si todavía hay datos históricos en `usage.json` que la referencian; el admin las muestra como "no catalogadas" y eso ya está manejado, pero borrar reduce la trazabilidad.
- **No hardcodees el nombre del modelo en `admin/bot.py`** para los avisos. Toda la lógica de límites y display del admin pasa por `core/llm_limits.py` — si necesitás algo nuevo, agregá un helper al módulo.

## Estado actual

- Modelo de chat por default: `llama-3.3-70b-versatile`
- Modelo de audio: `whisper-large-v3`
- Tier de Groq de referencia: **free**
- Catálogo: `core/llm_limits.py`
- Override manual del TPD para los avisos: `GROQ_DAILY_TOKEN_LIMIT` en `.env`
