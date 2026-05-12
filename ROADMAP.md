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
- También acepta texto plano (útil para pruebas sin micrófono)
- Handler unificado para voz y texto (un solo pipeline)
- Mantiene historial de conversación durante la sesión (últimos 10 mensajes)

### Personalidad y comportamiento
- Perfil completo del adulto mayor en `perfil.md` (lenguaje natural, editable)
- El familiar define: quién es la persona, familia, gustos, salud, reglas del bot
- Temas sensibles (guerras, política): da una oración breve y neutral, redirige
  al bienestar de la persona sin mentir ni profundizar
- Nombre del asistente configurable (hoy: Clara)

### Detección de angustia y alertas
- El LLM clasifica cada respuesta con DISTRESS_LEVEL 0-3 (oculto para Rosa)
  - 0: normal · 1: tristeza/soledad · 2: angustia · 3: emergencia
- Si el nivel supera 0, el bot familiar recibe una alerta automática con
  timestamp, fragmento de lo que dijo Rosa y lo que respondió Clara
- Cooldown por nivel para evitar spam: 60 min (nivel 1), 30 min (nivel 2), sin límite (nivel 3)
- Si el LLM omite la línea DISTRESS_LEVEL, el sistema asume 0 y no falla
- Módulos separados: `core/distress.py` (parsing + cooldown) y `core/alerts.py` (envío)

### Memoria y registro
- **Aprendizajes automáticos**: después de cada conversación, el LLM extrae
  datos nuevos relevantes y los anota en `perfil.md` bajo `## Aprendizajes`
- **Log diario**: cada intercambio queda registrado en `logs/YYYY-MM-DD.md`
  con hora, lo que dijo Rosa y lo que respondió Clara

### Recordatorios proactivos (scheduler)
- Saludo diario configurable (default: 08:30)
- Recordatorios de medicamentos u otros eventos (hora y mensaje configurables)
- El bot inicia la conversación sin que Rosa tenga que escribir

### Bot familiar (canal separado)
- Segundo bot de Telegram exclusivo para el familiar
- `/perfil` — muestra el perfil completo actual
- `/editar` — edita cualquier sección del perfil con menú interactivo
- `/ayuda` — lista de comandos
- Recibe alertas automáticas cuando Rosa muestra señales de angustia

### Seguridad
- Secretos en `.env` (nunca en el repo): BOT_TOKEN, CHAT_ID, GROQ_API_KEY
- `.gitignore` protege `.env`, `venv/`, logs y caché
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
      resumen del día (temas charlados, estado anímico detectado, recordatorios cumplidos)
- [ ] **Comando /log en bot familiar**: que el familiar pueda pedir el log
      del día desde Telegram sin acceder al archivo

### Media prioridad
- [ ] **Historial persistente**: hoy el historial de conversación se pierde
      al reiniciar el bot. Guardarlo en disco para mantener continuidad entre sesiones

### Baja prioridad / Ideas
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
| Runtime | Python 3.14, macOS |
