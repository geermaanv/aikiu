# Aikiu — contexto para asistentes de IA

Acompañante conversacional por Telegram para personas mayores que viven solas.
Dos trabajos: **conversar** de forma que quiera volver a hablar mañana, y
**avisarle a la familia** cuando algo anda mal.

La usuaria real es Marta, 83 años, **lúcida** (sin deterioro cognitivo). Todavía
no lo recibió: hay una sola oportunidad de primera impresión.

---

## Las tres reglas que más importan

1. **Antes de tocar una regla de comportamiento, leé `CAMBIOS.md` y corré
   `bash spec.sh <tema>`.** El 22/07 se agregó una regla de largo "porque no
   existía": existía en otra sección y decía lo contrario. Un grep cuesta diez
   segundos.

2. **Lo que se puede verificar con código NUNCA va al LLM.** Vive en
   `core/calidad.py`, compartido por el gate y el monitoreo nocturno. Un LLM
   marcó "me imagino lo lindos que se ven" como uso de tuteo; un regex no
   comete ese error.

3. **Nada puede fallar hacia el silencio.** Es un sistema de alerta. Todo
   `except` en el camino de una alerta degrada hacia avisar de más. El vigía
   devolvía nivel 0 ("todo bien") ante cualquier excepción, y con la cuota de
   API agotada "no sé volver a mi casa" quedó registrado como sin novedad.

---

## Qué hay y dónde

| | |
|---|---|
| `aikiu.py` | monolito (~2.600 líneas). **No partirlo** — ~900 tests parchean rutas concretas. |
| `aikiu_core.md` | reglas de comportamiento del conversador, en prosa. Hot-reload. |
| `core/calidad.py` | chequeos determinísticos. **Fuente de verdad única.** |
| `core/distress.py`, `alerts.py` | clasificación de riesgo y aviso a la familia |
| `simulador/` | genera conversaciones contra el código de producción |
| `simulador/aserciones.json` | qué cuenta como falla, y cuáles van por código |
| `simulador/niveles.json` | gate por niveles, criterio binario sin tolerancia |
| `kb/` | 21 libros de gerontología indexados + búsqueda semántica local |
| `PROPUESTA_PROTOCOLOS.md` | propuesta de refactor **refutada por su propio experimento**. Archivada. |

**Cosas no obvias que ya existen** (verificar antes de construir):

- `aikiu._monitoreo_calidad_bot` — corre cada noche sobre las conversaciones
  **reales** y avisa al bot admin.
- `aikiu.red_emergencia` — clasificación de respaldo por patrones, sin LLM.
- `aikiu._menciona_fallecido_en_presente` — detector con inferencia por edad.
- `simulador/correr_vigia.py` — banco de casos del clasificador de riesgo.
- `simulador/juez_libros.py` — explorador con RAG. **No es un gate**: acertó
  1 de 4 y dos de sus errores eran dañinos.

---

## Comandos

```bash
bash start.sh                                        # los 3 bots
./venv/bin/python -m pytest tests/ -q                # ~4 s, siempre
bash spec.sh <tema>                                  # antes de cambiar una regla
./venv/bin/python simulador/correr_vigia.py          # banco de riesgo, ~3 min
./venv/bin/python simulador/ciclo.py -e <esc> -n 8   # un escenario, ~8 min
./venv/bin/python simulador/ciclo.py -l 1 -n 8       # nivel completo, ~30 min
```

**Cuánta muestra:** una falla que ocurre el 5% de las veces tiene ~55% de
probabilidad de no aparecer en 16 corridas. Un verde con muestra chica no es
verde — pasó el 22/07. Para fallas sutiles, 8 reps mínimo.

---

## Trampas conocidas

- **GLM-5 en OpenRouter tiene picos de cola de hasta 139s** para la misma
  respuesta que normalmente tarda 5s. Con timeout corto, cada pico cae a Groq y
  agota su cuota diaria (100k tokens), que es la red de seguridad de la
  conversación. El trabajo de lote usa `_chat_create(timeout_s=...)` largo.
- **OpenRouter devuelve HTTP 200 con contenido vacío.** No es excepción: sin
  chequearlo, el fallback no se activa.
- **Groq se agota rápido.** Cuando pasa, Aikiu emite una frase de cortesía que
  el juez debe descartar — no es comportamiento, es infraestructura.
- **No tocar `aikiu_core.md` mientras corre el gate**: contamina la medición.
- **El repo es público.** Nunca commitear texto de los libros (`kb/kb.sqlite` y
  `kb/vectores.npy` están gitignoreados), ni `.env`.

---

## Cómo se conversa acá

Español rioplatense, voseo estricto. Varias verificaciones son sobre el
registro, así que no se puede simplificar cambiando el idioma.

La latencia importa: es la queja principal de los testers. Nada que agregue una
llamada de LLM al camino de la respuesta.
