# Errores recurrentes y lecciones

Lo que ya salió mal, para no repetirlo. **Un error entra acá cuando ocurre por
segunda vez**, o cuando la primera fue lo bastante cara.

No es un diario: es una lista de trampas. Si algo de acá se puede convertir en
un test o en un chequeo automático, se convierte y se anota el reemplazo — una
lección que depende de que alguien la recuerde ya falló una vez.

---

## 1. Declarar algo arreglado con muestra insuficiente

**Ocurrió dos veces el mismo día (22/07/2026).**

- Se arregló el bug de "familiar fallecido", se probó a mano una vez, salió
  bien y se declaró resuelto. Con 2 repeticiones del escenario fallaba 2/2.
- Se corrió el gate del nivel 1 con 16 conversaciones: cero fallas, se declaró
  GANADO. Con 36 conversaciones volvió a rojo.

**Por qué pasa:** las fallas de comportamiento son intermitentes. Una que
ocurre el 5% de las veces tiene ~55% de probabilidad de no aparecer en 16
corridas.

| para ver una falla del... | hacen falta |
|---|---|
| 20% | ~10 corridas |
| 10% | ~25 corridas |
| 5% | ~50 corridas |

**Regla:** ninguna prueba manual exitosa prueba nada. El criterio de éxito se
define ANTES, con su número de corridas. Y las fallas más sutiles —la
conversación base— necesitan MÁS muestra que las dramáticas, no menos.

---

## 2. Cambiar una regla sin mirar qué dice el sistema hoy

**22/07/2026.** Se agregó una regla de largo de respuesta afirmando que "no
existía ninguna". Existía en otra sección del núcleo y decía lo contrario
(*hasta 5 oraciones para recetas*). Las respuestas largas no eran un olvido:
**había una regla autorizándolas**.

El mismo día, un arreglo introdujo la violación de otra regla: se escribió
"ofrecé seguir" y el modelo respondió *"¿te sigo con el frito o al horno?"*,
que es un menú A/B, prohibido.

**Por qué pasa:** con 105 reglas en 25 secciones nadie tiene el conjunto en la
cabeza, ni siquiera quien edita el archivo todos los días.

**Regla:** `bash spec.sh <tema>` antes de tocar nada. Cuesta diez segundos.
→ automatizado en `spec.sh`, campos 2 y 3 de `CAMBIOS.md`.

---

## 3. Construir algo que ya existía

**22/07/2026.** Se reimplementaron 13 chequeos de calidad que ya existían en
`aikiu._monitoreo_calidad_bot`, corriendo cada noche sobre las conversaciones
reales. Cuatro de ellos, además, se reimplementaron **peor**: pasando por un
LLM en vez de un regex.

Se descubrió por accidente, al escribir la herramienta de especificación.

**Regla:** antes de construir, grep. `CLAUDE.md` lista lo no obvio que ya
existe. → parcialmente automatizado en `spec.sh`, campo 4.

---

## 4. Un medidor equivocado es peor que ninguno

**22/07/2026.** De 22 fallas que reportó el gate, **9 eran falsos positivos del
propio juez**: el valor real del dólar marcado como dato inventado, un cierre
cálido leído como positividad tóxica, y tres veces seguidas "comentale al
médico" — que es la conducta que la regla exige.

Antes de eso, el evaluador de notas 0-10 daba ±5 puntos de varianza sobre el
mismo texto, y el loop perseguía mejoras de 0.2. No era una meseta: era ruido.

**Reglas:**
- Nada de notas de 0-10 dadas por un LLM. Aserciones binarias, y el juez debe
  citar la frase textual que prueba la falla.
- **Lo verificable con código nunca va al LLM.** Vive en `core/calidad.py`.
- Toda aserción nueva lleva casos de control en imperativo ("NO MARQUES como
  falla que..."). Precisar en tono descriptivo no alcanzó dos veces.
- Un chequeo determinístico equivocado es MÁS peligroso que uno probabilístico:
  nadie lo pone en duda. El detector de tuteo marcaba "tuyo", que es correcto
  en rioplatense.

---

## 5. Cuando un prompt no alcanza, el problema no es la redacción

**Dos veces, con el mismo desenlace.**

- La omisión del token de clasificación de riesgo (~65% de las veces). Tres
  reescrituras del prompt fallaron. Se resolvió **separando el clasificador**
  en un agente propio.
- El bug de "familiar fallecido". Tres versiones de la regla, estancado en 3/5.
  Se resolvió **sacando la decisión del prompt**: un detector en código que
  inyecta la directiva solo en el turno que la necesita.

**Matiz importante, medido el 22/07:** el aislamiento NO era la causa de la
mejora. Un experimento con tres condiciones mostró que el mismo texto siempre
presente da el mismo resultado que cargado condicionalmente (22/25 los dos).
Lo que mejora es **cómo está escrita la regla**: imperativa, con las frases
textuales de lo que el modelo dijo mal. 15/25 → 22/25.

**Regla:** si una regla falla dos veces seguidas, no la reescribas una tercera
en el mismo tono. O se pasa a código, o se reescribe imperativa con los
ejemplos textuales de la falla.

---

## 6. Nada puede fallar hacia el silencio

**22/07/2026.** `clasificar_distress` devolvía `(0, "")` ante cualquier
excepción, y nivel 0 significa "todo bien". Con la cuota de Groq agotada,
*"no sé volver a mi casa"* y *"ya no tiene sentido nada de esto"* quedaron
registrados como sin novedad. La familia no se habría enterado nunca.

Lo encontró un banco de casos corriendo solo, no una revisión de código.

**Regla:** todo `except` en el camino de una alerta degrada hacia avisar de
más. → cubierto por `aikiu.red_emergencia` y `tests/test_red_emergencia.py`.

---

## 7. Optimizar para el usuario equivocado

**21-22/07/2026.** Se trabajaron 48 horas en protocolos de deterioro cognitivo
—familiar fallecido, extravío, acusaciones de robo, delirium— cuando la usuaria
real **no tiene deterioro cognitivo**. Mientras tanto, el nivel 1 del gate
(conversación base: saludo, monosílabos, soledad), que es lo único que ella va
a vivir todos los días, estaba en rojo y sin verificar.

**Regla:** antes de arrancar algo, preguntar *¿esto lo va a vivir la usuaria
real en las primeras dos semanas?*. Si la respuesta es no, va al backlog.

---

## 8. Un documento de arquitectura no es progreso

**22/07/2026.** Se escribió una propuesta de refactor de 6.600 palabras. El
experimento que la propia propuesta pedía como criterio de falsación la refutó
el mismo día: la mejora venía de la redacción, no de la arquitectura.

El documento igual valió la pena, pero **no por lo que proponía**: valió porque
obligó a escribir la sección "qué me haría abandonar esta propuesta", y al
escribirla apareció la variable que nunca se había separado.

**Regla:** toda propuesta grande escribe primero su criterio de falsación, y lo
corre antes de implementar nada. Si el criterio no se puede escribir, la
propuesta no está lo bastante definida para ejecutarse.
