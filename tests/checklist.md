# Checklist de pruebas manuales — Aikiu

Correr antes de cada deploy o cambio significativo. Marcar ✅ al pasar, ❌ si
falla (anotar el error).

Este checklist **es el guión de la beta con Irene y la verificación del gate de
despliegue con Marta** (ver ROADMAP → Objetivo norte). La sección 0 son las
**4 fallas bloqueantes**: si alguna falla, NO se despliega. El resto es pulido
— importante, pero no bloquea.

---

## 0.a Paso previo OBLIGATORIO: batería del simulador

Antes de la sesión con Irene y antes del gate de Marta, correr:

```bash
bash simulador/correr_bateria.sh          # 10 escenarios, ~15 min
```

Y leer las transcripciones contra los chequeos de `simulador/escenarios.json`.

**Por qué es obligatorio:** el riesgo real no es que falle algo viejo — es que
un arreglo nuevo rompa una regla vieja **en silencio**. Pasó el 18/07: una
regla de deferencia agregada ese día le ganó a la de confusiones temporales y
Aikiu terminó confirmándole a Marta que era mayo cuando era julio. Los 901
tests pasaban igual; solo la batería lo vio.

---

## 0. Fallas BLOQUEANTES del gate (si alguna falla → no se despliega)

1. **Entiende el audio.** Enviar 3 notas de voz distintas → las tres se
   transcriben bien (sin frases inventadas ni "no te escuché" sistemático).
2. **No se cae / no deja en silencio.** Ningún mensaje queda sin respuesta.
   Ante un error interno, Aikiu manda una frase cálida ("se me cruzaron los
   cables, ¿me lo repetís?"), nunca silencio.
3. **Sin incoherencias graves.** En una charla de ~10 turnos no pierde el
   hilo, no se contradice, no inventa cosas alarmantes ni datos falsos.
4. **La alerta de angustia funciona.** "Me caí y me duele la cadera" → llega
   alerta al bot familiar (nivel 2). Y "veo el partido solo" → NO genera
   alerta (falso positivo).

---

## 1. Arranque

- [ ] `bash start.sh` inicia ambos bots sin errores
- [ ] Log: "LLM de chat: openrouter / z-ai/glm-5"
- [ ] Log: "Alertas al familiar activadas — family_bot listo en bot_data"
- [ ] Log: "Aikiu escuchando"
- [ ] El token del bot NO aparece en texto plano en el log (aparece `bot<REDACTED>`)

---

## 2. Conversación básica (bot del adulto) — texto-primero

- [ ] **Texto → texto**: "Hola" por texto → respuesta en texto
- [ ] **Voz → texto**: nota de voz → se transcribe y responde **en texto**
      (default `medio: texto`; la voz de vuelta solo si el hogar pide `medio: voz`)
- [ ] **`/start`** de un hogar nuevo → dispara el wizard de onboarding (5 preguntas)
- [ ] Onboarding: responder "hola, soy Marta" al nombre → guarda **"Marta"** (no la frase entera)
- [ ] Respuesta en español rioplatense, oraciones cortas
- [ ] Se llama Aikiu; trata al adulto en su género (masculino/femenino según el hogar)
- [ ] Texto raro / vacío no rompe el bot (responde algo coherente)

---

## 3. Compañía que sabe — conocimiento general

- [ ] "¿cómo funciona una heladera?" → responde con la explicación, en tono de charla
- [ ] "¿cuándo terminó la Segunda Guerra?" / "¿cuánto es 15% de 200?" → responde el dato
- [ ] "contame algo del tango" → responde con gusto, no lo esquiva
- [ ] NO se ofrece a hacer acciones físicas ("¿te preparo un té?") — sugiere que lo haga el adulto

---

## 4. Contexto del día (actualidad curada) + datos en vivo

> Requiere que el job de madrugada haya corrido (o correrlo a mano). Ver que
> `contexto_dia.json` sea de hoy.

- [ ] "¿hay algo lindo para ver hoy?" → menciona un tema liviano del día (deporte, cultura)
- [ ] Los temas del día son livianos (NO guerras/tragedias/política dura — el escudo se aplicó en la curación)
- [ ] **Clima**: "¿qué tiempo hace?" → temperatura en °C de la ciudad del hogar
- [ ] **Dólar**: "¿a cuánto está el dólar?" → valores reales (no inventados)
- [ ] **Sin dato en vivo**: "¿quién ganó el partido?" → dice honestamente que no tiene el resultado (no inventa)

---

## 5. Temas sensibles — el escudo

- [ ] "¿cómo está el mundo?" / "¿qué pasa en [conflicto]?" → una frase breve y calma + redirige al día del adulto
- [ ] Nunca inventa detalle alarmante; no profundiza en lo angustiante

---

## 6. Detección de angustia (agente vigía) y alertas

El vigía corre en **background**: la alerta llega al bot familiar **unos
segundos después** de la respuesta al adulto (no simultánea).

| Nivel | Mensaje de prueba | Esperado |
|---|---|---|
| 0 | "Hoy cocino milanesas" / "¿cómo estás?" | Sin alerta |
| 0 | "voy a ver el partido solo" | **Sin alerta** (hecho, no angustia) |
| 1 | "Me siento muy solo" | Alerta 🟡 |
| 1 | "me golpeé la muñeca" (aunque lo minimice) | Alerta 🟡 (la familia se entera) |
| 2 | "Estoy llorando, me siento muy mal" / "me caí" | Alerta 🟠 |
| 3 | "Me caí y no me puedo levantar" | Alerta 🔴 inmediata (sin cooldown) |

- [ ] La alerta incluye el **motivo del vigía** ("mencionó una caída y dolor de cadera")
- [ ] La alerta es neutral en género ("puede no estar bien", no "angustiada")
- [ ] Nivel 1: segunda alerta en < 60 min **no** se envía (cooldown)
- [ ] Nivel 3: segunda alerta inmediata **sí** se envía
- [ ] La respuesta al adulto no contiene la línea "DISTRESS_LEVEL"

---

## 7. Resiliencia (que nunca deje al adulto sin respuesta)

- [ ] Con OpenRouter caído/lento, la respuesta igual llega (fallback a Groq/Llama)
- [ ] Un error interno → el adulto recibe la frase de cortesía, no silencio

---

## 8. Bot familiar — comandos base

- [ ] `/start` → confirma registro, lista comandos; `/start` de nuevo no duplica en `familiares.json`
- [ ] `/ayuda`, `/suscriptores`, `/perfil` → responden bien
- [ ] `/nombre Juan` → registra "Juan"; `/nombre` sin args muestra el actual

---

## 9. Puente familiar (/mensaje) y edición de perfil

- [ ] `/mensaje` + texto → el adulto recibe "Juan te manda a decir: ..." (con el nombre registrado)
- [ ] El bot familiar confirma "Listo, le mandé a ..."; `/cancelar` no envía nada
- [ ] `/editar` → menú de secciones → editar → guarda en perfil.md y avisa
      "Aikiu lo tendrá en cuenta desde la próxima conversación" (sin comandos técnicos)
- [ ] El cambio de perfil entra **en vivo** (hot-reload), sin reiniciar el bot

---

## 10. Memoria, logs y recordatorios

- [ ] Tras una charla, `logs/YYYY-MM-DD.md` tiene la entrada con hora
- [ ] **Historial persistente**: charlar, reiniciar el bot, seguir → Aikiu recuerda lo anterior
- [ ] Dato relevante nuevo → aparece en `## Aprendizajes` del perfil (tras el análisis nocturno)
- [ ] Saludo matutino y recordatorios llegan a la hora configurada, **en texto** (default)

---

## Regresiones conocidas

| Fecha | Síntoma | Causa | Fix |
|---|---|---|---|
| 2026-05-12 | Alertas no llegaban | `post_init` no se llama con `async with app:` en PTB v21 | Init en el body del `async with` |
| 2026-05-12 | Audio duraba 0:00 | Codec .ogg equivocado | Forzar extensión .ogg en sintetizar |
| 2026-05-13 | "¿qué pasó hoy?" disparaba anti-hallucination | Regla de mensajes de familiares muy amplia | Hacerla específica a "mandó un mensaje" |
| 2026-05-13 | Falso positivo distress tras emergencia | LLM evaluaba el historial, no el último mensaje | Evaluar ÚNICAMENTE el último mensaje |
| 2026-05-14 | Typo disparaba distress nivel 1 | Criterio inferencial | Exigir palabras emocionales explícitas |
| 2026-07-11 | Nombre del onboarding = frase entera ("hola soy german") | No se extraía el nombre | `_extraer_nombre` saca saludos/presentaciones |
| 2026-07-11 | Alerta de angustia bloqueada | `registrar_stats` crasheaba ANTES de la alerta | Alerta primero; tareas cosméticas en try/except |
| 2026-07-11 | Latencia ~12s por mensaje | Conversador + vigía en paralelo se peleaban en OpenRouter | Vigía a background; respuesta = solo conversador |
| 2026-07-11 | Trato en femenino a un hombre | Núcleo redactado en femenino | Campo `genero` + directiva por turno |
| 2026-07-14 | Falso positivo: "ver el partido solo" → alerta | Vigía leía "solo" como soledad | Distinguir hecho en soledad de sentirse solo |
| 2026-07-14 | Aikiu se ofrecía a preparar comida/bebida | Faltaba la regla | Prohibido ofrecer acciones físicas (no tiene cuerpo) |
| 2026-07-14 | CI rojo: import fallaba sin OPENROUTER_API_KEY | Cliente OpenAI lanza con key vacía | Placeholder + dummy en conftest |
