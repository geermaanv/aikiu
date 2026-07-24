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

## Cómo se prueba Aikiu (rehecho el 21–22/07)

El loop viejo (`simulador/evaluador.py`, notas 0-10) no medía nada: la MISMA
conversación evaluada 4 veces daba ±5 puntos en un criterio y ±0.8 en el total,
y el loop perseguía mejoras de 0.2. No era una meseta en 8.5, era ruido. Peor:
`evaluador.py` promovía el cambio cuando el ruido subía el promedio.

Ahora hay tres piezas con roles distintos, y **no hay que confundirlas**:

| pieza | rol | binario | costo |
|---|---|---|---|
| `simulador/correr_vigia.py` | banco de casos: mensaje → nivel esperado | sí | muy bajo |
| `simulador/ciclo.py` + `juez.py` | gate por niveles, aserciones fijas | sí | medio |
| `simulador/juez_libros.py` | explorador: busca fallas que nadie anticipó | **no** | alto |

El **explorador no es un gate** y no puede escribir reglas solo: en la corrida
de validación acertó 1 de 4, y dos errores eran dañinos (recuperó un pasaje
sobre final de vida y lo aplicó a una señora que esperaba a su marido). Su
trabajo es levantar la mano, no tener razón. Entre "levantó la mano" y "es una
regla" va una persona.

**El loop de mejora es la conexión entre los tres:**

```
libros → casos nuevos → conversación → el explorador encuentra una falla
                                             ↓  (la confirma un humano)
                              se congela como aserción permanente
                                             ↓
                          el gate binario la verifica para siempre
```

Lo que mejora sin parar no es el juez: es **el banco de aserciones, que solo
crece**. Cada falla descubierta una vez queda atrapada. Por eso la diversidad
de casos es el cuello de botella real y no la medición — un amigo con 2
mensajes destapaba más que 40 conversaciones simuladas porque traía situaciones
que no estaban en la lista, no porque fuera humano.

Los libros dejaron NotebookLM y son locales: `kb/indexar.py` (10.373 chunks de
19 libros) + `kb/semantico.py` (embeddings multilingües por ONNX, sin torch ni
API). La consulta va en español y encuentra el pasaje en inglés sin traducir.

---

## Lo próximo a arreglar — resultado del gate completo (23/07)

Primera corrida entera de los 3 niveles, dos pasadas cada uno (~240
conversaciones, instrumento unificado, sin cortes). Ver
`noche_20260723_131520.md` y `spec.sh` antes de tocar cada regla.

**Las fallas firmes (en las dos pasadas) colapsan en 3 familias, no 10 bugs:**

1. **Aikiu pregunta e insiste de más al cerrar el turno** — es la más grande y
   la de mayor impacto. La forman: `G2` (dos preguntas), `G10` (menú A/B),
   `G17` ("che" cerrando pregunta), `G19` (interrogatorio, >50% de turnos con
   pregunta), `G20` (cierra la sesión con pregunta abierta). Son la MISMA
   conducta. Atacar primero, probablemente con una o dos reglas en formato
   imperativo (no cinco). Es lo primero de la spec `001`.
2. **Respuesta larga** — `G8` (>3 oraciones) y `G14` (cortada). El largo ya
   bajó de 27/65 a ~6/32 pero no cierra.
3. **Eco léxico** (`G5`) e **infantilización** (`G6`), sueltas.

**Ningún nivel está verde de forma estable:** algunos pases dan 🟢 y otros 🔴 en
el mismo nivel → las fallas son intermitentes (5-12%), justo lo que la muestra
grande destapa. El vigía (seguridad) sí está perfecto: no aparece en ninguna
falla.

**Casos nuevos de los libros** esperando revisión en
`simulador/casos_vigia_revisar.jsonl`. Hueco conocido: "creo que la vecina me
robó las tijeras" da nivel 0 y debería avisar (el vigía es ciego a la paranoia).

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
