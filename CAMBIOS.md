# Cómo se especifica un cambio de comportamiento

Antes de tocar `aikiu_core.md`, el prompt del vigía o cualquier regla, se
completa este formato. No es burocracia: es la lista de las cinco cosas que
generaron retrabajo el 22/07, cada una con el paso que la habría evitado.

**La regla de fondo:** no se cambia nada hasta poder decir *cómo voy a saber
que quedó bien*. El 22/07 el mismo bug se "arregló" tres veces porque cada
arreglo se validó con una prueba manual exitosa en vez de con un criterio
definido de antemano.

---

## El formato

```markdown
### [qué se cambia]

**1. Evidencia** — la frase textual, copiada de una transcripción real.
   No "a veces contesta largo". Sí: la respuesta de 7 oraciones del 22/07.

**2. Qué dice el sistema HOY** — grep, no memoria.
   `grep -n "largo\|oraciones" aikiu_core.md`

**3. Con qué choca** — qué otras reglas tocan el mismo terreno.
   `grep -in "<tema>" aikiu_core.md` y leer las vecinas.

**4. Criterio de éxito** — el comando exacto y el número exacto.
   `./venv/bin/python simulador/ciclo.py -e soledad -n 8` → S-SOL1 en 0/8

**5. Control: qué NO debe cambiar** — la lista de lo que ya funcionaba y
   podría romperse. Con su comando.
```

---

## Por qué cada campo

**1. Evidencia textual.** El experimento del 22/07 mostró que una regla con las
frases reales que el modelo dijo mal funciona mucho mejor que una descriptiva:
15/25 → 22/25. La evidencia no es solo para diagnosticar — **es el ingrediente
de la regla**. Sin la cita, la regla sale abstracta y se aplica a medias.

**2. Qué dice el sistema hoy.** El 22/07 se agregó una regla de largo
afirmando que "no existía ninguna". Existía en otra sección y decía *hasta 5
oraciones para recetas*: las respuestas largas no eran un olvido, había una
regla autorizándolas. Con 105 reglas en 25 secciones nadie tiene el conjunto en
la cabeza — **ni siquiera quien edita el archivo todos los días.** Un grep
cuesta diez segundos.

**3. Con qué choca.** Dos de los cinco bugs de ese día fueron choques sin
precedencia declarada: "visita esperada" le ganaba a "familiar fallecido", y
antes una regla de deferencia le había ganado a la de confusión temporal. Si
dos reglas tocan el mismo terreno, hay que escribir cuál manda **en el texto de
la regla**, no dejarlo librado al modelo.

**4. Criterio de éxito, con muestra.** Dos partes y las dos importan:

- *El comando*: si no se puede escribir el comando que lo verifica, el cambio
  no está definido. Es la tercera pata de detectar/manejar/**evaluar**.
- *El número*: un "verde" con muestra chica no es verde. El 22/07 el nivel 1
  dio cero fallas en 16 conversaciones y volvió a rojo con 36. **Una falla que
  ocurre el 5% de las veces tiene ~55% de probabilidad de no aparecer en 16
  corridas.** Referencia rápida:

  | para detectar una falla del... | hacen falta |
  |---|---|
  | 20% | ~10 corridas |
  | 10% | ~25 corridas |
  | 5%  | ~50 corridas |

  Las fallas de comportamiento sutiles viven en el 5-15%. Por eso los
  escenarios de conversación base necesitan **más** repeticiones que los
  dramáticos, no menos.

**5. Control.** Un arreglo del 22/07 introdujo una violación de otra regla: se
agregó "ofrecé seguir" y el modelo respondió *"¿te sigo con el frito o al
horno?"*, que es un menú A/B, prohibido. Todo cambio de comportamiento puede
romper algo que ya funcionaba, y el gate solo lo ve si se corre entero.

---

## Lo mismo para una aserción del juez

Una aserción mal escrita cuesta tanto como un bug: de las 22 fallas que reportó
el gate el 22/07, **9 eran falsos positivos del propio juez** y cada uno costó
una investigación. Marcó como falla el valor real del dólar, un cierre cálido,
y tres veces seguidas "comentale al médico" — que es la conducta que la regla
exige.

Por eso toda aserción nueva lleva:

- **la falla**, en positivo y concreta (qué tiene que aparecer en el texto)
- **casos de control**: dos o tres ejemplos de lo que **NO** debe marcar, en
  imperativo. "NO MARQUES como falla que le sugiera consultar al médico."
  Precisar la nota en tono descriptivo no alcanzó las dos primeras veces.
- **si se puede verificar con código, va con código.** Cero varianza, cero
  costo. El LLM marcó "me imagino lo lindos que se ven" como uso de tuteo.

---

## Cuánto cuesta verificar

Para elegir el criterio del campo 4 sin pedir de más:

```
un escenario × 8 reps          ~8 min     un cambio acotado
nivel 1 completo (4 esc × 8)   ~30 min    tocaste algo transversal
gate completo (13 esc)         ~2 h       antes de desplegar
banco del vigía (39 casos)     ~3 min     tocaste el clasificador de riesgo
pytest                         ~4 s       siempre
```

Cuando el cambio es de una regla puntual, el criterio es un escenario — no el
gate completo. Pedir de más hace que no se corra.
