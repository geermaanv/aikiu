# Aikiu — Estado del proyecto

Asistente conversacional para adultos mayores vía Telegram. Sin hardware
especial ni servidor propio. La documentación técnica completa (arquitectura,
features, instalación) vive en el **README**; el deploy y multi-tenant en
**MULTI_TENANT.md**. Este archivo es el **estado y el plan**.

---

## Objetivo norte (10/07/2026)

Una sola métrica decide si Aikiu funciona: **que Marta (la usuaria real) inicie
la conversación por gusto y mantenga 7 diálogos en 14 días** — ventana móvil,
medible desde `stats.json`; cuentan solo las conversaciones que inicia ella, no
las respuestas al saludo matutino.

- La periferia (multi-tenant, admin, website, inversores) queda **congelada**
  hasta que la métrica norte muestre retención real.
- Circuito de conocimiento (KB gerontológica → perfil): **manual**, sin
  automatizar mientras se aprende qué funciona.

### Gate de despliegue con Marta — con fecha (no "cuando se sienta natural")

"Desplegar cuando se sienta natural" siempre puede pedir una semana más. En su
lugar, un gate con fecha y una lista de fallas **bloqueantes** verificables.

**Cadena de validación:** simulador → beta con Irene (guión) → Marta → métrica norte.

- **Beta con Irene** — semana del **27/07/2026**. Prueba con guión estructurado;
  valida el funcionamiento natural con una persona real antes de gastar la única
  primera impresión con Marta. El feedback se incorpora antes del gate.
- **Gate de Marta** — objetivo: **primeros días de agosto** (fecha exacta el dom
  26/07). Se despliega SALVO que aparezca una de estas fallas bloqueantes:
  1. No entiende el audio (transcripción falla de forma sistemática).
  2. Se cae / no responde (silencio ante un mensaje).
  3. Incoherencias graves (pierde el hilo, inventa cosas alarmantes).
  4. No dispara la alerta de angustia ante una señal real (o falsas en cascada).

  "Todavía no se siente 100% natural" **NO** es bloqueante — es la excusa que
  estira para siempre. La mudanza y septiembre presionan: no correr la ventana
  más allá de principios de agosto.

**Tareas (dom 26/07):** fijar fecha exacta de Marta + confirmar bloqueantes;
coordinar sesión con Irene.

---

## Estado actual (post-beta, 11–18/07/2026)

El bot corre en Telegram real (Germán como tester), end-to-end: onboarding,
conversación con GLM-5, y detección de angustia con alerta a la familia
(confirmada llegando en un dispositivo real). **901 tests, CI en verde.**

**Arquitectura:**
- **GLM-5** (`z-ai/glm-5` vía OpenRouter, razonamiento apagado) como LLM de
  chat; Groq queda para la transcripción de voz (Whisper). Fallback automático
  a Groq/Llama si OpenRouter falla o tarda.
- **Agente vigía**: la detección de angustia es una llamada LLM separada
  (`clasificar_distress`) que corre en background — resolvió la omisión del
  ~65% del nivel de distress y no suma latencia. El conversador solo conversa.
- **Núcleo** `aikiu_core.md`: 76 reglas (podado de 92, dedup validado).
- **Hot-reload** de perfil.md / aikiu_core.md (cambios sin reiniciar el bot).
- **Género** configurable por hogar (inferido del nombre).

**Alertas con indagación previa (18/07):**
- Nivel 1-2 → NO se avisa de inmediato: queda **pendiente**, Aikiu repregunta
  y un segundo pase decide con la respuesta: *confirma* (avisa), *descarta*
  (era menor, no se molesta a la familia) o *sin datos* (sigue abierta).
- Nivel 3 (emergencia) → alerta **inmediata**, sin indagar.
- **Sin respuesta a los 10 min** → alerta igual, avisando que no contestó: el
  silencio tras un síntoma es más grave, no menos (job cada 2 min).
- La alerta incluye los **últimos 6 mensajes** de la charla, para que la
  familia vea cómo se llegó a la situación.
- La regla de salud cubre **síntomas** (náuseas, mareos, fiebre, falta de
  aire…), no solo dolores; los minimizadores ("un poco", "es la edad") ya no
  bajan el nivel — la confirmación previa filtra lo trivial.

**Resiliencia — nunca dejar al adulto sin respuesta:**
- Error handler global (frase cálida ante cualquier crash), timeout de 20s por
  llamada al LLM, y `generar_respuesta` nunca devuelve vacío.
- **Respuesta vacía de OpenRouter** (HTTP 200 con content vacío, intermitente)
  se trata como falla → cae a Groq. Antes el vigía la leía como "nivel 0" y
  **perdía alertas en silencio**.

**Memoria e higiene:**
- Historial de conversación **persistente** (sobrevive a reinicios) y podado a
  40 mensajes.
- Rotación de logs + redacción del token del bot en los logs.

**Producto (del feedback del beta):**
- **Texto-primero** (`medio` por hogar, default `texto`): la voz de edge-tts
  suena metálica; se retoma cuando haya un TTS mejor.
- **Compañía que sabe**: responde preguntas de conocimiento general (cómo
  funciona algo, historia, recetas, cálculos, idiomas).
- **Contexto del día**: job de madrugada que lee Google News (general + local
  por ciudad); un LLM **cura y filtra** dejando solo temas livianos — el escudo
  ante noticias duras se aplica ahí, una vez. Suma dólar y clima. Aikiu queda
  "al tanto" (ej: "hoy juega la semifinal del Mundial") para responder y para
  traer temas por iniciativa.

**Simulador sobre el camino real (18/07):** dejó de rearmar un prompt paralelo
y ahora corre sobre un hogar de prueba llamando a `generar_respuesta` /
`clasificar_distress` — el mismo camino que producción. Antes era
estructuralmente incapaz de ver los bugs del beta (no pasaba por la resolución
de config, ni inyectaba contexto del día ni el aviso de historial multi-día).
Nueva persona **Héctor** (79, Rosario, hombre, parco, minimiza síntomas) para
cubrir género masculino y otra ciudad. Dos escenarios nuevos cierran las clases
de bug que el simulador no podía ver: **`correccion`** (el adulto lo corrige y
desconfía → cubre "contradecir inventando" y "disculparse de más") y
**`dia_siguiente`** con el flag `--continuar`, que conserva el historial entre
corridas para simular otro día → cubre "dato con fecha viejo repetido como
actual". Ambos validados en vivo.

**Bugs del beta arreglados:** nombre del onboarding ("hola soy german"), alerta
bloqueada por crash de stats, latencia (~12s → ~3s), género hardcodeado, falso
positivo del vigía ("ver el partido solo" no es angustia), Aikiu ofreciéndose a
hacer acciones físicas ("¿te preparo un té?"), `/setname` (ya dice "Aikiu"),
**contexto del día viejo repetido como actual** (historial multi-día),
**contradecir al usuario inventando un dato para sostenerse**, **`genero` y
`medio` del hogar ignorados** por `_config_hogar` (fallaba en silencio), y
**disculparse por errores no cometidos** ante una simple preferencia.

**Lección del beta:** cada persona nueva que lo prueba destapa una clase
distinta de falla. 4 mensajes de un amigo valieron más que 40 conversaciones
simuladas — de ahí la cadena simulador → Irene → Marta.

---

## Pendientes

**Producto:**
- Calibración fina del vigía con datos reales de uso.
- Resumen diario al familiar (temas charlados, estado anímico, recordatorios).
- Comando `/log` en el bot familiar (pedir el log del día sin tocar archivos).
- Métricas de aislamiento (alerta silenciosa si el volumen de mensajes cae >50%).
- Dashboard de engagement (los datos ya se acumulan en `stats.json`).
- Voz más natural (ElevenLabs u otro TTS) antes de reactivar el audio.
- Datos deportivos en vivo (resultado del partido) — requiere una API de deportes.

**Deuda técnica diferida, con criterio** (NO ahora, a propósito — refactors
grandes y riesgosos, sin beneficio para el objetivo norte y con riesgo de
regresión justo después de un beta que funciona):
- **Split del monolito** (`aikiu.py`, ~2000 líneas): ~890 tests parchean rutas
  concretas (`patch("aikiu.groq")`, `aikiu.CONFIG`, etc.); mover funciones a
  otros módulos rompe esos parches. Hacer solo si una feature grande lo justifica.
- **Neutralizar el género en el núcleo**: la directiva por turno ya funciona;
  reescribir las ~28 apariciones de "la usuaria" podría degradar el caso
  femenino (Marta, la usuaria real). El approach actual alcanza.

---

## Stack técnico
| Capa | Tecnología |
|---|---|
| LLM de chat | GLM-5 (`z-ai/glm-5`) vía OpenRouter |
| STT (voz → texto) | Groq Whisper large-v3 |
| TTS (texto → voz) | edge-tts + ffmpeg — en pausa (texto-primero) |
| Bot Telegram | python-telegram-bot 21.6 |
| Scheduler | APScheduler 3.10 |
| Tests | pytest (901 tests) |
| Actualidad / datos | Google News RSS (curado) + dolarapi + wttr.in |
| Deploy | Railway + volumen persistente (`AIKIU_REGISTRY`) — ver MULTI_TENANT.md |
| Runtime | Python 3.11+ (desarrollo en 3.14), macOS/Linux/Windows |
