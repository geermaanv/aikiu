# Checklist de pruebas manuales — Aikiu

Correr antes de cada deploy o cambio significativo.
Marcar con ✅ al pasar, ❌ si falla (anotar el error).

---

## 1. Arranque

- [ ] `bash start.sh` inicia ambos bots sin errores
- [ ] Log muestra "Alertas al familiar activadas — family_bot listo en bot_data"
- [ ] Log muestra "Aikiu escuchando"

---

## 2. Conversación básica (bot de Marta)

- [ ] **Texto → texto**: enviar "Hola" por texto → Marta recibe respuesta en texto (no audio)
- [ ] **Voz → voz**: enviar nota de voz → Marta recibe audio de Aikiu
- [ ] **`/start`**: enviar `/start` → Aikiu responde con un saludo (no silencio)
- [ ] La respuesta usa español rioplatense, máximo 3 oraciones
- [ ] Aikiu se llama Aikiu (no Marta, no "yo soy el asistente")
- [ ] Texto desconocido no rompe el bot (responde algo coherente)

---

## 3. Tool calling — consultas al mundo real

- [ ] **Clima BA**: "¿qué tiempo hace hoy?" → responde con temperatura en °C y sensación térmica de Buenos Aires
- [ ] **Clima ciudad**: "¿hace frío en Córdoba?" → consulta Córdoba específicamente, no Buenos Aires
- [ ] **Dólar**: "¿a cuánto está el dólar?" → responde con blue y oficial, compra y venta con valores exactos en pesos
- [ ] **Noticias**: "¿qué noticias hay hoy?" → responde con 3-4 titulares reales
- [ ] **Noticias 2**: "¿qué pasó hoy?" → activa herramienta de noticias (NO la regla de mensajes de familiares)
- [ ] **Sin tool**: "¿cómo estás?" → respuesta directa, no llama herramientas, no genera alerta

---

## 4. Temas sensibles

- [ ] **Guerra/política**: "¿qué pasa en Ucrania?" → una oración neutra + redirige a Marta
- [ ] **Catástrofe**: "¿qué pasó con el terremoto?" → misma lógica: una oración + redirige
- [ ] **Nunca inventa**: la oración de contexto es vaga pero no falsa

---

## 5. Detección de angustia y alertas

| Nivel | Mensaje de prueba | Esperado |
|-------|-------------------|----------|
| 0 | "Hoy cocinamos milanesas" | Sin alerta |
| 0 | "¿cómo estás?" | Sin alerta (pregunta neutral) |
| 1 | "Me siento muy sola" | Alerta 🟡 al bot familiar |
| 2 | "Estoy llorando, me siento muy mal" | Alerta 🟠 al bot familiar |
| 3 | "Me caí y no me puedo levantar" | Alerta 🔴 inmediata, sin cooldown |

- [ ] La alerta llega al bot familiar con timestamp, fragmento de Marta y respuesta de Aikiu
- [ ] Nivel 1: segunda alerta en menos de 60 min **no** se envía (cooldown)
- [ ] Nivel 3: segunda alerta inmediata **sí** se envía (sin cooldown)
- [ ] DISTRESS_LEVEL no aparece en ningún mensaje que recibe Marta

---

## 6. Bot familiar — comandos base

- [ ] `/start` → confirma registro, lista todos los comandos (incluye `/nombre` y `/mensaje`)
- [ ] `/start` de nuevo → "ya estabas registrado", no duplica en `familiares.json`
- [ ] `/ayuda` → lista todos los comandos incluyendo `/nombre`
- [ ] `/suscriptores` → muestra nombre y chat_id de cada familiar registrado
- [ ] `/perfil` → muestra perfil.md completo

---

## 7. Bot familiar — nombre para Marta

- [ ] `/nombre` sin argumentos → muestra el nombre registrado actualmente
- [ ] `/nombre Juan` → registra "Juan" y confirma
- [ ] Enviar `/mensaje` luego un texto → Marta recibe "Juan te manda a decir: ..."

---

## 8. Bot familiar — editar perfil

- [ ] `/editar` → muestra menú de secciones con botones y lista de texto
- [ ] Elegir sección → muestra contenido actual y pide nuevo
- [ ] Enviar nuevo contenido → sección actualizada en perfil.md, mensaje dice **"Aikiu lo tendrá en cuenta desde la próxima conversación"** (sin mencionar bash ni comandos técnicos)
- [ ] "❌ Cancelar" → cancela sin modificar
- [ ] `/cancelar` durante la edición → cancela sin modificar

---

## 9. Puente familiar (/mensaje)

- [ ] `/mensaje` → bot pide el mensaje
- [ ] **Texto**: familiar envía texto → Marta recibe **texto** con el nombre del familiar
- [ ] **Audio**: familiar envía nota de voz → Marta recibe **audio** de Aikiu con el mensaje sintetizado
- [ ] El bot familiar confirma con "Listo, le mandé a Marta: ..."
- [ ] `/cancelar` durante `/mensaje` → cancela sin enviar nada a Marta

---

## 10. Memoria y logs

- [ ] Después de una conversación, `logs/YYYY-MM-DD.md` tiene la entrada con hora
- [ ] Dato relevante nuevo → aparece en `## Aprendizajes` de perfil.md (puede tardar unos segundos)

---

## 11. Recordatorios proactivos (verificar config.yml)

- [ ] A la hora configurada de saludo, Marta recibe audio con **fecha** ("Hoy es miércoles 20 de mayo") y **temperatura** ("Hoy en Olivos hay X grados")
- [ ] Si la API de clima no responde, el saludo se envía igual con la fecha pero sin temperatura
- [ ] A las horas de medicamento, Marta recibe el recordatorio en audio

---

## Casos críticos — verificar siempre después de cualquier cambio

| # | Mensaje | Resultado esperado |
|---|---------|-------------------|
| A | "¿qué tiempo hace?" | Responde con °C (no solo descripción) |
| B | "¿a cuánto está el dólar?" | Activa herramienta (no dice "no tengo info") |
| C | "¿qué pasó hoy?" | Muestra noticias (no activa regla de mensajes de familiares) |
| D | "¿cómo estás?" | No genera alerta de distress |
| E | "me siento muy sola" | Genera alerta distress nivel 1 |
| F | /mensaje desde el familiar | Llega a Marta con el nombre correcto |
| G | Cualquier mensaje | DISTRESS_LEVEL no aparece en el texto |

---

## Regresiones conocidas

| Fecha | Síntoma | Causa | Fix |
|-------|---------|-------|-----|
| 2026-05-12 | Alertas no llegaban | `post_init` no se llama con patrón `async with app:` en PTB v21 | Mover init al body del `async with` |
| 2026-05-12 | Audio duraba 0:00 | Salida .ogg pero codec equivocado | Forzar extensión .ogg en sintetizar |
| 2026-05-12 | Aikiu se presentaba como Rosa (nombre de la usuaria) | System prompt ambiguo | Explicitar "Tu nombre es X, hablás con Y" |
| 2026-05-12 | /mensaje texto → audio | Siempre llamaba a responder_con_voz | Preservar medio original del familiar |
| 2026-05-13 | Tools no se activaban (dólar, noticias) | System prompt no mencionaba herramientas disponibles | Agregar hint explícito de tools en el prompt |
| 2026-05-13 | "¿qué pasó hoy?" disparaba anti-hallucination | Regla de mensajes de familiares era demasiado amplia | Hacer la regla específica a "mandó un mensaje" |
| 2026-05-13 | Falso positivo distress nivel 1 | Criterios no aclaraban que aplica solo al estado de Marta | Agregar "solo cuando Marta describe su propio estado" |
| 2026-05-13 | "bash start.sh" visible al familiar tras editar perfil | Mensaje técnico hardcodeado en recibir_contenido | Reemplazar por mensaje amigable |
| 2026-05-13 | Falso positivo distress — "Hola" → nivel 2 tras emergencia | LLM evalúa historial completo, no solo el mensaje actual | Instrucción explícita: evaluar ÚNICAMENTE el último mensaje |
| 2026-05-13 | Tools no activan para clima/dólar/noticias | Hint genérico en prompt insuficiente | Listar triggers exactos en español con mapeo → herramienta |
| 2026-05-13 | "Quien es" no reconocido en /editar (sin tilde) | Comparación exacta de strings | Normalizar con unicodedata antes de comparar |
| 2026-05-14 | "manana" (typo) disparaba distress nivel 1 | Criterio inferencial, no requería palabras explícitas | Exigir palabras emocionales exactas; conservador ante ambigüedad |
| 2026-05-14 | Saludo matutino sin temperatura | Greeting estático hardcodeado | saludo_matutino() consulta clima y lo incluye en el saludo |
