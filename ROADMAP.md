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
- El LLM clasifica cada respuesta con DISTRESS_LEVEL 0-3 (oculto para Rosa)
  - 0: conversación normal, pregunta informativa, saludo
  - 1: Rosa expresa soledad, tristeza, que no duerme bien, que extraña a alguien
  - 2: llora, dice que está muy mal, dolor persistente, confusión/desorientación,
       caída reciente (aunque haya pasado), "soy una carga", no querer molestar
  - 3: emergencia activa ahora mismo (no puede levantarse, dolor de pecho, pide ayuda)
- Los criterios de nivel ≥1 solo aplican cuando Rosa describe su propio estado
  emocional o físico — preguntas neutras o saludos son siempre nivel 0
- Si el nivel supera 0, el bot familiar recibe una alerta automática con
  timestamp, fragmento de lo que dijo Rosa y lo que respondió Clara
- Cooldown por nivel: 60 min (nivel 1), 30 min (nivel 2), sin cooldown (nivel 3)
- Si el LLM omite la línea DISTRESS_LEVEL, el sistema asume 0 y no falla
- Módulos separados: `core/distress.py` (parsing + cooldown) y `core/alerts.py` (envío)

### Memoria y registro
- **Aprendizajes automáticos**: después de cada conversación, el LLM extrae
  datos nuevos relevantes y los anota en `perfil.md` bajo `## Aprendizajes`
- **Log diario**: cada intercambio queda registrado en `logs/YYYY-MM-DD.md`
  con hora, lo que dijo Rosa y lo que respondió Clara

### Recordatorios proactivos (scheduler)
- Saludo diario con temperatura: cada mañana Clara dice la temperatura actual de
  la ciudad de Rosa (Olivos, Buenos Aires) antes de preguntar cómo amaneció.
  Si la API de clima falla, el saludo se envía igual sin temperatura.
  La ciudad es configurable en `config.yml` → `ciudad`
- Recordatorios de medicamentos u otros eventos (hora y mensaje configurables)
- El bot inicia la conversación sin que Rosa tenga que escribir

### Bot familiar (canal compartido)
- Segundo bot de Telegram para toda la familia — no requiere configuración por familiar
- Cualquier familiar manda `/start` y queda suscripto automáticamente
- `/nombre [nombre]` — registra cómo te conoce Rosa (usado en el puente familiar)
- `/mensaje` — **puente familiar**: el familiar envía texto o audio y Clara se lo
  transmite a Rosa preservando el medio (texto → texto, voz → voz sintetizada).
  Usa el nombre registrado con `/nombre`, no el username de Telegram
- `/perfil` — muestra el perfil completo actual
- `/editar` — edita cualquier sección del perfil con menú interactivo
- `/suscriptores` — lista de familiares registrados
- `/ayuda` — lista de comandos
- Alertas automáticas llegan a **todos** los suscriptores cuando Rosa muestra angustia
- `subscribers.json` y `familiares.json` excluidos del repo

### Consultas al mundo real (tool calling)
- El LLM decide cuándo consultar herramientas externas usando Groq native tool calling
- **Clima**: wttr.in — temperatura, sensación térmica, descripción, humedad
- **Dólar**: dolarapi.com — blue y oficial, compra y venta
- **Noticias**: RSS de La Nación — top 4 titulares, filtrables por tema
- Si la API falla, el bot responde con un mensaje de error amigable sin romper la conversación
- Módulo separado: `core/tools.py` (definiciones + fetch + dispatcher)

### Tests y calidad
- **89 unit tests** con pytest cubriendo:
  - `core/distress.py`: parsing del LLM, cooldowns por nivel, casos borde
  - `core/tools.py`: dispatcher, parsing RSS (CDATA + fallback), filtro por tema,
    límite de 4 titulares, manejo de errores HTTP en las tres herramientas
  - Lógica de perfil: lectura/escritura de secciones, gestión de suscriptores
  - Reglas del system prompt: hint de tools, anti-hallucination específico a
    mensajes de familiares, criterios de distress con nivel 0 para saludos/preguntas
  - DISTRESS_LEVEL nunca visible para Rosa, criterios de caídas y "soy una carga"
- Checklist manual E2E en `tests/checklist.md` + `tests/lista_manual.txt`
- Git pre-commit hook: los 90 tests corren automáticamente antes de cada commit

### Seguridad
- Secretos en `.env` (nunca en el repo): BOT_TOKEN, CHAT_ID, GROQ_API_KEY
- `.gitignore` protege `.env`, `venv/`, logs, caché y datos personales
- Ambos bots solo responden a los chat_id autorizados
- `.env.example` como plantilla pública

### Setup y operación
- `bash setup.sh` — instala dependencias en entorno virtual
- `bash start.sh` — arranca ambos bots en paralelo (familiar es opcional)
- `bash configurar.sh` — wizard guiado para armar el perfil.md desde cero
- `config.yml` — configuración no sensible: nombre, voz, modelo, recordatorios

---

## Pendiente

### Alta prioridad
- [ ] **Resumen diario al familiar**: cada noche enviar por Telegram un
      resumen del día a todos los suscriptores (temas charlados, estado anímico, recordatorios)
- [ ] **Comando /log en bot familiar**: que cualquier familiar pueda pedir el log
      del día desde Telegram sin acceder al archivo

### Media prioridad
- [ ] **Variedad en la conversación**: hoy Clara repite los mismos temas del perfil
      (plantas, tangos, familia). Mejoras: instrucción al LLM para variar basándose
      en el historial de la sesión y la sección `## Aprendizajes`; posibilidad de
      que el familiar sugiera temas nuevos vía `/editar` o un comando `/temas`
- [ ] **Historial persistente**: hoy el historial de conversación se pierde
      al reiniciar el bot. Guardarlo en disco para mantener continuidad entre sesiones
- [ ] **Métricas de aislamiento**: cronjob que evalúe la frecuencia de mensajes
      de Rosa. Si el volumen cae por debajo del 50% del promedio semanal, enviar
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
| Tests | pytest 9.0 (90 tests) |
| Runtime | Python 3.14, macOS |
