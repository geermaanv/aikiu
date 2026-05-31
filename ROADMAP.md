# Aikiu — Estado del proyecto

## Qué es
Asistente de voz para adultos mayores via Telegram. Sin hardware especial, sin
servidor propio. Corre en cualquier Mac con Python.

---

## Funcionalidad actual

### Conversación
- Recibe mensajes de voz y los transcribe (Groq Whisper large-v3)
- Genera respuestas con LLM (Groq llama-3.3-70b-versatile)
- Responde con audio de voz (edge-tts + ffmpeg, voz argentina femenina)
- También acepta texto plano — responde en el mismo medio (texto → texto, voz → voz)
- Mantiene historial de conversación durante la sesión (últimos 10 mensajes)

### Personalidad y comportamiento
- Perfil completo del adulto mayor en `perfil.md` (lenguaje natural, editable)
- El familiar define: quién es la persona, familia, gustos, salud, reglas del bot
- Temas sensibles (guerras, política): da una oración breve y neutral, redirige
  al bienestar de la persona sin mentir ni profundizar
- Nombre del asistente configurable (hoy: Clara)
- No da consejos médicos: ante síntomas o dudas de medicación, siempre deriva
  al médico con calidez
- Caídas recientes, dolor físico y "soy una carga": manejo explícito con
  contención y sugerencia de consultar al médico o avisar a la familia

### Detección de angustia y alertas
- El LLM clasifica cada respuesta con DISTRESS_LEVEL 0-3 (oculto para Marta)
  - 0: conversación normal, pregunta informativa, saludo
  - 1: Marta expresa soledad, tristeza, que no duerme bien, que extraña a alguien
  - 2: llora, dice que está muy mal, dolor persistente, confusión/desorientación,
       caída reciente (aunque haya pasado), "soy una carga", no querer molestar
  - 3: emergencia activa ahora mismo (no puede levantarse, dolor de pecho, pide ayuda)
- Los criterios de nivel ≥1 solo aplican cuando Marta describe su propio estado
  emocional o físico — preguntas neutras o saludos son siempre nivel 0
- Si el nivel supera 0, el bot familiar recibe una alerta automática con
  timestamp, fragmento de lo que dijo Marta y lo que respondió Clara
- Cooldown por nivel: 60 min (nivel 1), 30 min (nivel 2), sin cooldown (nivel 3)
- Si el LLM omite la línea DISTRESS_LEVEL, el sistema asume 0 y no falla
- Módulos separados: `core/distress.py` (parsing + cooldown) y `core/alerts.py` (envío)

### Memoria y registro
- **Log diario**: cada intercambio queda registrado en `logs/YYYY-MM-DD.md`
  con hora, lo que dijo Marta y lo que respondió Clara
- **Análisis nocturno** (hora configurable, default 23:30): un job lee el log del día
  completo y hace un solo LLM call que:
  - Extrae aprendizajes nuevos sobre Marta comparando contra los ya existentes en `perfil.md`
    — evita duplicados por construcción
  - Detecta patrones problemáticos de la conversación (respuestas cortadas, preguntas
    innecesarias, temas evitados) y sugiere ajustes
  - Escribe los aprendizajes en `## Aprendizajes` y los ajustes en `## Ajustes sugeridos`
    de `perfil.md`, que Clara lee en la próxima conversación
  - Reemplaza el enfoque anterior (un LLM call extra por cada mensaje) — menos ruido,
    mejor calidad, sin costo por turno
  - Prompt estricto: el LLM compara cada dato contra los aprendizajes existentes antes
    de incluirlo — elimina duplicados y comentarios sobre el bot (no sobre Marta)
- **Estadísticas diarias** en `stats.json` (excluido del repo):
  - Por mensaje: contador, hora del primero y último, distress por nivel
  - Por análisis nocturno: aprendizajes nuevos y ajustes sugeridos del día
  - **Ranking de temas por engagement**: score calculado noche a noche combinando
    promedio de palabras por turno, ratio de receptividad alta, frecuencia de aparición
    y bonus si el tema aparece en los aprendizajes del perfil
  - Base de datos lista para un futuro dashboard familiar

### Recordatorios proactivos (scheduler)
- Saludo diario con fecha, temperatura y feriados: cada mañana Clara saluda a Marta
  diciendo el día de la semana y la fecha (por ej. "Hoy es miércoles 20 de mayo"),
  la temperatura actual de la ciudad y, si corresponde, si es feriado en Argentina
  (via date.nager.at). Si alguna API falla, el saludo se envía igual con los datos
  disponibles. La ciudad es configurable en `config.yml` → `ciudad`
- Recordatorios de medicamentos u otros eventos (hora y mensaje configurables)
- El bot inicia la conversación sin que Marta tenga que escribir

### Bot familiar (canal compartido)
- Segundo bot de Telegram para toda la familia — no requiere configuración por familiar
- Cualquier familiar manda `/start` y queda suscripto automáticamente
- `/nombre [nombre]` — registra cómo te conoce Marta (usado en el puente familiar)
- `/mensaje` — **puente familiar**: el familiar envía texto o audio y Clara se lo
  transmite a Marta preservando el medio (texto → texto, voz → voz sintetizada).
  Usa el nombre registrado con `/nombre`, no el username de Telegram
- `/perfil` — muestra el perfil completo actual
- `/editar` — edita cualquier sección del perfil con menú interactivo
- `/stats` — muestra estadísticas de los últimos 7 días (mensajes, horarios, alertas, aprendizajes)
- `/aprendizajes` — muestra los aprendizajes actuales y ajustes sugeridos del perfil
- `/suscriptores` — lista de familiares registrados
- `/ayuda` — lista de comandos
- Alertas automáticas llegan a **todos** los suscriptores cuando Marta muestra angustia
- `subscribers.json` y `familiares.json` excluidos del repo

### Consultas al mundo real (pre-routing determinístico)
- Detección de keywords en el mensaje de Marta antes de llamar al LLM (sin depender de tool calling del modelo)
- **Clima**: wttr.in — temperatura, sensación térmica, descripción, humedad
- **Dólar**: dolarapi.com — blue y oficial, compra y venta
- **Noticias**: RSS de La Nación — top 4 titulares, filtrables por tema
- Si la API falla, el bot responde con un mensaje de error amigable sin romper la conversación
- Módulo separado: `core/tools.py` (definiciones + fetch + dispatcher)

### Alertas de inactividad
- Si Marta no envía mensajes en N horas, el bot familiar recibe una alerta automática
- Umbral configurable en `config.yml` → `alerta_inactividad.horas_umbral` (default: 4 horas)
- Checks programados dos veces por día (default: 11:30 y 19:00), configurables
- Cooldown de un alerta por día: si ya se alertó hoy, no vuelve a alertar hasta mañana
- Sin baseline (bot recién arrancado): no genera alertas hasta recibir el primer mensaje
- Mensaje cálido y no alarmista: "Puede estar bien y simplemente no usó el bot, pero vale verificar"
- Se envía a todos los suscriptores del bot familiar
- Función: `verificar_inactividad()` en `aikiu.py` + `notify_inactividad()` en `core/alerts.py`

### Calidad conversacional (Estrategias activas)
- **Estrategia 1 — Iniciativa proactiva**: reglas explícitas en el perfil para que Clara
  no solo reaccione. Cuando la conversación se frena, Clara aporta un dato, anécdota
  o curiosidad antes de preguntar. Máximo una pregunta por respuesta; ante respuestas
  cortas de cierre ("nada", "no sé"), cambia de tema sin insistir.
- **Estrategia 2 — Blacklist de receptividad**: tras cada intercambio, un LLM call
  liviano (max_tokens=30) detecta el tema y la receptividad (alta/baja/neutra). Los
  temas con baja receptividad en las últimas 48h se excluyen automáticamente del
  siguiente turno. Los temas con alta receptividad se inyectan como sugerencia de
  iniciativa, tomados del ranking nocturno. Historial en `receptividad.json`.
- **Estrategia 3 — Matriz de rol dinámica**: si DISTRESS_LEVEL es 0, Clara puede
  usar humor liviano; si es ≥1, bloquea el humor completamente y activa modo
  contención hasta que Marta esté estable.

### Multi-tenant (varios adultos en un mismo deploy)
- Un mismo proceso atiende a múltiples adultos (un BOT_TOKEN, un GROQ_API_KEY
  compartidos). Cada adulto que mande `/start` queda dado de alta automático
  y se le crea su carpeta en `instances/<chat_id>/` con state, perfil, stats,
  familiares y logs aislados (módulo `core/hogar.py`)
- **Template global neutro**: `perfil.md` y `config.yml` de la raíz son
  un esqueleto sin nombres propios. Los datos reales de cada adulto viven
  exclusivamente en `instances/<chat_id>/state.json` (overrides) y
  `instances/<chat_id>/perfil.md`. `configurar.py --template` regenera el
  esqueleto; `configurar.py --chat-id <id>` configura un hogar puntual
- **Wizard de onboarding** en el bot principal: el primer `/start` de un
  adulto dispara una `ConversationHandler` de 5 preguntas (nombre, edad,
  ciudad, familia, gustos) que acepta texto **y** voz (transcripción
  Whisper). El progreso se persiste turno a turno en `state.json` por si
  se corta la conversación. `/saltar` y `/cancelar` para escapar
- **`/configurar` en el bot familiar**: 8 preguntas guiadas que el
  familiar contesta para armarle el perfil al adulto activo desde su
  propio Telegram. Reusa `configurar.generar_perfil()`
- **Migración idempotente** del single-tenant viejo: la primera vez que arranca
  `aikiu.py`, detecta los archivos en la raíz del repo (`state.json`,
  `perfil.md`, etc.) y los mueve a `instances/<owner_chat_id>/`. Marca el state
  con `migrated_from_legacy: true` para auditar (módulo `core/migrate_legacy.py`)
- **Familiares many-to-many**: un familiar puede vincularse a varios adultos.
  El adulto genera un código de invitación con `/invitar` (6 caracteres
  alfanuméricos sin ambigüedad, 24h de vida, single-use) y el familiar lo
  consume con `/vincular <CODIGO>`. El bot familiar gestiona el "adulto activo"
  con `/misadultos` y `/elegir <chat_id>` (módulos `core/invites.py` +
  `core/familiar_state.py`)
- **Alertas por hogar**: cada `notify_family()` apunta al `familiares.json`
  del hogar correcto. Los familiares solo reciben alertas de los adultos a
  los que están vinculados, identificadas por nombre del adulto
- **Admin multi-tenant**: nuevos comandos `/hogares` (lista los hogares con
  alta, familiares y actividad) y `/borrar <chat_id>` (borrado de hogar en
  dos pasos con confirmación explícita)
- **Deploy en Railway**: `Procfile` con tres procesos (worker + familiar +
  admin), `railway.json` con restart automático, `AIKIU_REGISTRY` apuntando
  a un volumen persistente (`/data/instances`) para que los hogares
  sobrevivan a redeploys. Detalle completo en `MULTI_TENANT.md`
- **Backward-compatible**: las firmas públicas de `core/state.py`,
  `core/alerts.py` y los handlers viejos siguen aceptando los parámetros
  originales — instalaciones single-tenant existentes siguen andando sin
  cambios después de la migración

### Tests y calidad
- **821 tests** con pytest, **97% de cobertura global** (unit + integración E2E):
  - `core/distress.py`, `core/tools.py`, `core/alerts.py`, `core/heartbeat.py`,
    `core/state.py`, `core/usage.py`, `core/tts.py`, `core/llm_limits.py`,
    `core/instance.py`, `core/utils.py` — 93–100% por módulo
  - `aikiu.py` (99%): `cargar_config`, `transcribir`, `generar_respuesta`,
    `analisis_nocturno`, ranking de temas, filtros médicos, alertas de síntomas
    persistentes, recordatorios, `main()` end-to-end
  - `andromarta/` (87–100%): persona, memoria, estado, ciclo, scheduler, generador
    y bot — incluye validación de config y ciclo completo de conversación
  - `admin/bot.py` (94%) + `admin/state.py` (99%): handlers (/start, /ayuda,
    /admins, /quitar_admin, /health, /llm, /metricas, /logs, /instancias),
    helpers de formateo, gestión multi-admin con env override
  - `familiar_bot.py` (99%): suscripción, edición de perfil por secciones,
    puente de mensajes texto/voz con transcripción Whisper
  - `configurar.py` (99%): wizard interactivo completo
  - **Integración E2E** (`tests/test_integration_e2e.py`): 8 flujos punta a punta
    atravesando varios módulos (TOFU + alerta, ciclo Andromarta, puente familiar,
    /llm agregado, análisis nocturno con perfil real, /health, edición de perfil)
- Receptividad, distress, system prompt y reglas anti-hallucination siguen cubiertos
- Checklist manual E2E en `tests/checklist.md`
- Git pre-commit hook: los 821 tests corren automáticamente antes de cada commit
- **Multi-tenant** (47 tests nuevos): `core/hogar.py`, `core/invites.py`,
  `core/familiar_state.py`, migración legacy, flujo `/invitar` + `/vincular`
  + `/misadultos` + `/elegir`, comandos legacy operando sobre el adulto
  activo, `notify_family` con prefijo por adulto, admin `/hogares` y
  `/borrar` en dos pasos

### Seguridad
- Secretos en `.env` (nunca en el repo): BOT_TOKEN, GROQ_API_KEY,
  FAMILIAR_BOT_TOKEN, ADMIN_BOT_TOKEN
- `.gitignore` protege `.env`, `venv/`, logs, caché, datos personales,
  e `instances/` (datos de los hogares multi-tenant)
- Self-service onboarding: cualquier `/start` crea un hogar — la
  protección contra abuso debe venir de fuera (link de invitación,
  limitación de polling, etc.). El admin bot puede borrar hogares con
  `/borrar <chat_id>` si aparece uno indeseado
- `.env.example` como plantilla pública

### Setup y operación
- `bash setup.sh` — instala dependencias en entorno virtual
- `bash start.sh` — arranca ambos bots en paralelo (familiar es opcional)
- `bash configurar.sh` — wizard guiado para armar el perfil.md desde cero
- `config.yml` — configuración no sensible: nombre, voz, modelo, recordatorios
- `nombre_adulto_mayor` en `config.yml` es la única fuente de verdad del nombre:
  se propaga al system prompt, logs, recordatorios y prompt de aprendizajes automáticamente

---

## Pendiente

### Alta prioridad
- [ ] **Resumen diario al familiar**: cada noche enviar por Telegram un
      resumen del día a todos los suscriptores (temas charlados, estado anímico, recordatorios)
- [ ] **Comando /log en bot familiar**: que cualquier familiar pueda pedir el log
      del día desde Telegram sin acceder al archivo

### Media prioridad
- [x] **Variedad en la conversación**: resuelto con las 3 estrategias de calidad
      conversacional (iniciativa proactiva, blacklist de receptividad, matriz de rol)
- [ ] **Dashboard de engagement**: visualizar el ranking de temas por score,
      evolución de receptividad y métricas de engagement desde el bot familiar
      o una interfaz web liviana. Los datos ya se acumulan en `stats.json`.
- [ ] **Historial persistente**: hoy el historial de conversación se pierde
      al reiniciar el bot. Guardarlo en disco para mantener continuidad entre sesiones
- [ ] **Métricas de aislamiento**: cronjob que evalúe la frecuencia de mensajes
      de Marta. Si el volumen cae por debajo del 50% del promedio semanal, enviar
      una alerta silenciosa al bot familiar indicando posible apatía o aislamiento.

### Baja prioridad / Ideas
- [x] **Tool calling**: implementado con wttr.in, dolarapi.com y RSS de La Nación.
- [ ] **Sanitización de datos (privacy-by-design)**: capa local de ofuscación
      de datos médicos/personales antes de enviar el payload a la API de Groq.
      Mitiga riesgos en ausencia de certificaciones formales (relevante si se
      posiciona contra alternativas como Ato que venden privacidad certificada).
- [ ] **Voz más natural**: edge-tts (es-AR-ElenaNeural) suena metálica.
      Evaluar ElevenLabs (pago, alta calidad) o aguardar que Groq reintegre
      TTS en español. Priorizar cuando haya usuario real usando el bot a diario.
- [ ] **Configurador via Telegram**: que el familiar pueda armar el perfil
      respondiendo preguntas en el bot familiar, sin tocar archivos
- [ ] **Panel web**: interfaz simple para editar perfil y ver logs desde
      el navegador, sin necesidad de Telegram ni archivos

---

## Stack técnico
| Componente | Tecnología |
|---|---|
| STT (voz → texto) | Groq Whisper large-v3 |
| LLM | Groq llama-3.3-70b-versatile |
| TTS (texto → voz) | edge-tts + ffmpeg (OGG OPUS) |
| Bot Telegram | python-telegram-bot 21.6 |
| Scheduler | APScheduler 3.10 |
| Tests | pytest 9.0 (821 tests, 97% cobertura) |
| Multi-tenant | `core/hogar.py` + `core/invites.py` + `core/familiar_state.py` |
| Deploy | Railway con `Procfile` + volumen persistente (`AIKIU_REGISTRY`) |
| Runtime | Python 3.11+ (desarrollo en 3.14), macOS/Linux/Windows |
