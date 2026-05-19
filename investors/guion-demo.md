# Guion de demo en vivo — Aikiu

Demo para inversores. Duración objetivo: 6–7 minutos. Producto real, sin slides durante esta parte.

---

## 0. Antes de empezar (checklist de pre-vuelo)

Hacer 30–60 min antes de la reunión. Si algo de esto falla, no improvisar en vivo: usar el plan B (ver más abajo) o el video grabado.

- [ ] `bash start.sh` corriendo, log muestra "Aikiu escuchando" y "Alertas al familiar activadas"
- [ ] Internet estable (la demo depende de Groq, wttr.in, dolarapi.com, RSS de La Nación)
- [ ] Dos teléfonos/ventanas visibles y proyectables:
  - **Teléfono A** — Telegram de Marta (el adulto mayor). Habla con "Clara".
  - **Teléfono B** — Telegram del bot familiar (lo que ve la familia).
- [ ] Volumen del teléfono A al máximo: la respuesta de Clara es audio y tiene que escucharse en la sala
- [ ] `perfil.md` revisado: que no muestre datos sensibles o ruido si se proyecta
- [ ] Hacer una conversación de prueba completa y borrar el historial de pantalla
- [ ] Tener a mano un **video de respaldo** (2–3 min) con la demo grabada, por si la conexión falla
- [ ] Cargar batería de ambos teléfonos

---

## 1. El gancho (30 seg, antes de tocar el teléfono)

> "Mi mamá, Marta, tiene 83 años y vive sola. Yo no puedo llamarla cada hora, pero tampoco puedo dejar de pensar en si está bien. Aikiu es lo que construí para ese problema. No es una maqueta — está corriendo ahora mismo, y Marta lo usa todos los días. Se los muestro en vivo."

Dejar el teléfono A a la vista. No explicar la arquitectura todavía — que lo vean funcionar primero.

---

## 2. Secuencia de demo

Cada paso: **qué hacer** → **qué decir mientras carga** → **plan B**.

### Paso 1 — Conversación por voz (90 seg)

**Qué hacer:** desde el teléfono A, mandarle a Clara una nota de voz natural, ej:
*"Hola Clara, ¿cómo estás? Hoy me desperté con ganas de cocinar algo rico."*

**Qué decir mientras carga:** "Marta habla, no escribe. No tuvo que aprender una app nueva ni comprar nada — es el Telegram que ya tenía. Clara transcribe, entiende y le responde con voz."

**Resultado esperado:** Clara responde con audio, voz argentina, máximo 3 oraciones, cálida.

**Plan B:** si el audio tarda o falla, mandar el mismo mensaje por **texto** — Clara responde en texto y la demo sigue. Si Groq está caído, pasar al video de respaldo.

---

### Paso 2 — Consultas al mundo real (45 seg)

**Qué hacer:** mandar por voz o texto: *"¿Qué tiempo hace hoy?"* y después *"¿A cuánto está el dólar?"*

**Qué decir:** "No es solo charla. Clara puede traer información real — clima, dólar, noticias — sin que Marta tenga que abrir nada."

**Resultado esperado:** responde con temperatura en °C y con valores de dólar blue y oficial.

**Plan B:** si una API externa falla, el bot responde con un mensaje amable sin romperse — mencionarlo como feature ("ven que no se cae, degrada con elegancia") y seguir.

---

### Paso 3 — Detección de angustia y alerta a la familia (90 seg) — **el momento clave**

**Qué hacer:** desde el teléfono A, mandar un mensaje que simule una emergencia:
*"Me caí y no me puedo levantar."*

**Qué decir mientras carga:** "Esto es lo que diferencia a Aikiu de un chatbot. Clara no solo contiene a Marta con calidez — clasifica el nivel de angustia de cada mensaje. Y miren el otro teléfono."

**Resultado esperado:**
- Teléfono A: Clara responde a Marta con calidez y contención (sin tecnicismos).
- Teléfono B: llega una **alerta roja inmediata** al bot familiar con la hora, lo que dijo Marta y lo que respondió Clara.

**Mostrar el teléfono B a la sala.** Este es el "ajá".

**Plan B:** si la alerta no llega, probar con un mensaje de nivel más bajo (*"Me siento muy sola hoy"* → alerta amarilla). Si tampoco, pasar al video. No insistir más de una vez en vivo.

> Nota ética para decir en voz alta: "El nivel de angustia nunca lo ve Marta. Ella solo recibe compañía. La familia recibe la señal."

---

### Paso 4 — El puente familiar (45 seg)

**Qué hacer:** desde el teléfono B (bot familiar), mandar `/mensaje` y después un texto corto, ej: *"Mamá, te quiero, paso a verte mañana."*

**Qué decir:** "Y funciona en los dos sentidos. Cualquier familiar le puede mandar un mensaje y Clara se lo transmite a Marta con el nombre de quien lo mandó."

**Resultado esperado:** el teléfono A recibe el mensaje de parte del familiar.

**Plan B:** si falla, describirlo verbalmente y seguir — no es el momento central.

---

### Paso 5 — Proactividad (30 seg, opcional según tiempo)

**Qué hacer:** mostrar en el log o describir el saludo matutino y los recordatorios de medicación.

**Qué decir:** "Aikiu no espera a que Marta escriba. Cada mañana la saluda con la temperatura del día, le recuerda la medicación, y si pasa demasiadas horas sin actividad, avisa a la familia."

**Plan B:** este paso es narrado, no requiere acción en vivo. Si el tiempo apremia, saltearlo.

---

## 3. Cierre de la demo (15 seg)

> "Todo esto que vieron está corriendo hoy, con una usuaria real. Ahora sí, déjenme contarles a dónde va." → **pasar al pitch deck.**

---

## 4. Reglas de oro

- **Nunca depender de una sola toma.** Si un paso falla una vez, plan B y seguir. Dos intentos fallidos seguidos = cortar al video.
- **El audio tiene que escucharse.** Si la sala es grande, parlante externo conectado al teléfono A.
- **No proyectar `perfil.md` ni logs crudos** salvo que estén revisados — pueden tener datos sensibles de Marta.
- **El paso 3 es el corazón.** Si solo hay tiempo para uno, es ese.
- **No prometer features que no están.** Resumen diario, panel web e historial persistente están en el roadmap, no implementados — si preguntan, decir "en desarrollo".

---

## 5. Preguntas difíciles que pueden caer (y respuesta corta)

| Pregunta | Respuesta corta |
|---|---|
| ¿Y la privacidad de los datos médicos? | Hoy los datos van a la API de Groq. La sanitización local (privacy-by-design) está en el roadmap como prioridad. Honestidad: es un pendiente conocido. |
| ¿Qué pasa si se cae internet en la casa? | El bot corre sobre Telegram; si Marta tiene datos o WiFi, funciona. Sin conexión, no — es una limitación real del enfoque sin hardware. |
| ¿Cuántos usuarios tienen? | Una usuaria piloto real (Marta), uso diario. Estamos en etapa de validación, no de escala. |
| ¿Cómo ganan plata? | No es el objetivo. Es un modelo de eficiencia: el costo de operación es casi cero porque usa el celular existente. Se sostiene con donaciones y sponsors, gratis para las familias. |
| ¿La voz no suena robótica? | Sí, hoy usa edge-tts. Mejorar la voz está en el roadmap. Preferimos validar el valor antes de invertir en la voz premium. |
