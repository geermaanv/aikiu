# Arquitectura

Cómo está armado Aikiu y **por qué** cada decisión. Las razones importan más
que la descripción: varias parecen arbitrarias hasta que se sabe qué falló
antes.

---

## El sistema en una vista

```
   Telegram (adulto)                     Telegram (familia)      Telegram (admin)
         │                                      ▲                       ▲
         ▼                                      │                       │
   ┌───────────────┐                    ┌───────────────┐       ┌──────────────┐
   │  aikiu.py     │  alerta nivel 1-3  │ familiar_bot  │       │  admin/bot   │
   │  conversador  │───────────────────▶│               │       │              │
   └───────┬───────┘                    └───────────────┘       └──────▲───────┘
           │                                    ▲                      │
           │  cada mensaje                      │                      │ calidad
           ▼                                    │                      │ nocturna
   ┌───────────────┐   nivel 0-3                │               ┌──────┴───────┐
   │  vigía        │────────────────────────────┘               │ core/calidad │
   │ (2ª llamada)  │                                            └──────────────┘
   └───────────────┘
```

**Dos agentes, no uno.** El conversador y el clasificador de riesgo son
llamadas separadas. Pedirle al mismo modelo que converse cálido **y** se
autoclasifique hacía que omitiera la clasificación ~65% de las veces; tres
reescrituras del prompt no lo arreglaron. Ver `memory/learning.md` #5.

**El vigía corre en background.** En paralelo daba ~12s de latencia por
contención en el proveedor. La respuesta al adulto es una sola llamada; la
alerta a la familia llega unos segundos después.

---

## Stack

| capa | qué | por qué |
|---|---|---|
| LLM conversador | GLM-5 vía OpenRouter, razonamiento **apagado** | con razonamiento consume el `max_tokens` y devuelve contenido vacío |
| fallback | Groq / llama-3.3-70b | el adulto nunca puede quedarse sin respuesta |
| STT | Groq Whisper large-v3 | |
| TTS | edge-tts — **en pausa** | texto-primero; la voz no era lo bastante natural |
| bot | python-telegram-bot 21.6, long-polling | |
| datos | archivos JSON por hogar | sin base de datos: un hogar es un directorio |
| KB | 21 libros → SQLite FTS5 + embeddings ONNX locales | sin API, sin torch |

**Trampa de infraestructura:** GLM-5 en OpenRouter tiene picos de cola de hasta
139s (medido) para la misma respuesta que normalmente tarda 5s. Con un timeout
único y corto, cada pico caía a Groq y agotaba su cuota diaria de 100k tokens —
que es justamente la red de seguridad de la conversación. Por eso
`_chat_create` acepta `timeout_s`: el trabajo de lote espera, la conversación
no.

---

## Multi-tenant

Cada hogar es un directorio bajo `instances/<chat_id>/`:

```
state.json           quién es, ciudad, género, medio
perfil.md            quién es la persona (hot-reload)
historial.json       últimos 40 mensajes
familiares.json      quién recibe las alertas
contexto_dia.json    actualidad curada de esa ciudad
alerta_pendiente.json  alerta esperando confirmación
logs/YYYY-MM-DD.md   la charla del día
```

**Hot-reload:** `perfil.md` y `aikiu_core.md` se releen al cambiar de mtime. El
código Python no: requiere reiniciar.

---

## El comportamiento

| dónde | qué |
|---|---|
| `aikiu_core.md` | reglas del conversador, en prosa. Se manda entero en cada turno. |
| `_prompt_vigia()` | criterios de clasificación de riesgo, función pura y testeable |
| `core/calidad.py` | chequeos determinísticos — **fuente de verdad única** |
| detectores en código | casos donde una regla en prosa no alcanzó |

**Por qué hay reglas en prosa y detectores en código.** La prosa alcanza para
casi todo. Cuando una regla falla dos veces seguidas, se pasa a código: el
detector evalúa el turno e inyecta una directiva específica. Hoy hay uno
(`_menciona_fallecido_en_presente`). No es la arquitectura preferida — es la
excepción para lo que el prompt no sostiene.

**Lo que NO se hace:** modularizar el núcleo en protocolos cargados por
situación. Se propuso, se midió y se refutó: el aislamiento no mejora nada, lo
que mejora es la redacción. Ver `specs/done/000-protocolos-refutada.md` y
`memory/learning.md` #5.

---

## Alertas: cómo se decide molestar a la familia

```
mensaje ──▶ vigía ──▶ nivel 0  nada
                      nivel 1-2  alerta PENDIENTE + Aikiu repregunta
                                 └─▶ confirma ──▶ avisa
                                 └─▶ descarta ──▶ no avisa
                                 └─▶ 10 min sin aclarar ──▶ avisa igual
                      nivel 3  avisa YA, sin repreguntar
```

**Falla hacia avisar de más, nunca hacia el silencio.** Si el LLM no responde,
`red_emergencia()` clasifica por patrones literales sin nube. Devolver 0 ante
un error significaba decirle a la familia "todo bien" justo cuando el sistema
estaba ciego.

La alerta incluye los últimos 6 mensajes: una línea suelta no le sirve a nadie
para decidir si llamar.

---

## Verificación

Tres niveles, ordenados por costo. **Usar siempre el más barato que responda la
pregunta.**

| | qué responde | costo |
|---|---|---|
| `pytest` + `core/calidad.py` | ¿voseo? ¿largo? ¿markdown? | gratis, 4s |
| `simulador/correr_vigia.py` | ¿clasifica bien el riesgo? | ~3 min |
| `simulador/ciclo.py` | ¿sostiene una conversación entera? | 8 min–2 h |

Y aparte, **fuera del gate**: `simulador/juez_libros.py` explora contra los
libros para encontrar fallas que nadie anticipó. Acertó 1 de 4 en validación y
dos de sus errores eran dañinos: **no es criterio de aceptación**, su salida es
una cola de revisión humana.

El gate es binario y sin tolerancia: una sola falla deja el nivel en rojo. Un
criterio con tolerancia se vuelve negociable, y lo que se negocia no cierra
nunca.

---

## Decisiones diferidas, con criterio

- **Partir `aikiu.py`** (~2.600 líneas). ~900 tests parchean rutas concretas
  (`aikiu.groq`, `aikiu.CONFIG`); mover funciones rompe esos parches. Hacer solo
  si una feature grande lo justifica.
- **Mover el código a `src/`.** Mismo motivo.
- **Neutralizar el género en el núcleo.** La directiva por turno ya funciona;
  reescribir ~28 apariciones podría degradar el caso femenino, que es la
  usuaria real.
