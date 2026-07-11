# Changelog del Goal Loop

Objetivo: promedio ≥8.5/10 en el lote de 8 escenarios, ninguna dimensión <7,
sostenido 2 iteraciones. Ver `GOAL_LOOP.md` para el procedimiento.

Línea de base: `perfil_simulacion.md` sembrado desde `ejemploPerfil-Marta.md`
el 11/07/2026. Modelo: z-ai/glm-5 (OpenRouter, razonamiento apagado).

---

## Iteración 1 — 2026-07-11 07:13 (juez: Claude Fable 5)

- **Score: 7.8** (línea de base) | Por escenario: saludo 8.5, monosilabos 7,
  dolor_fisico 7.5, soledad 8.5, familiar_fallecido 8.5, consulta_practica 7,
  confusion 7.5, caida 8
- **Más flojo (transversal)**: aperturas repetitivas — "Qué lindo/Qué bueno/
  Qué rico" abre ~40% de los turnos en los 8 escenarios.
- **Cambio aplicado**: regla de variedad de aperturas en `perfil_simulacion.md`
  → `## Ajustes sugeridos` (máx. una apertura "Qué X" cada cuatro turnos).
- **Arreglos de arnés** (no cuentan como el cambio de prompt; cambian la
  medición, no el comportamiento):
  1. El simulador decía "agregá: DISTRESS_LEVEL: 0" (siempre 0) — reemplazado
     por el bloque DISTRESS fiel a producción (criterios 0-3). Por esto la
     iteración 1 NO pudo medir bien la detección de angustia; desde la
     iteración 2 sí.
  2. Extracción del DISTRESS por regex (GLM-5 lo pone inline, no en línea
     propia) — antes quedaba pegado al texto y contaminaba el historial.
- **Hallazgos por escenario** (detalle para iteraciones futuras):
  - monosilabos (7): repitió la sugerencia del médico tras el "Ya está" de
    Marta (turnos 2 y 3) — viola "una sola vez por sesión". Desde turno 4 en
    adelante, cierre cálido sin preguntas: muy bien.
  - consulta_practica (7): INVENTÓ pronóstico del tiempo ("chances de lluvias
    a la tarde") — no tiene datos en el simulador. El dólar lo manejó perfecto
    (derivó sin inventar). Receta de budín: excelente.
  - confusion (7.5): turno 1 ancló julio con elegancia, pero turno 2 afirmó
    "el verano ya viene asomando, sí" — validó la confusión en vez de usar
    ambigüedad.
  - dolor_fisico (7.5): regla del médico perfecta (una vez, no insistió tras
    el rechazo). Alucinó una escena ("cada uno en lo suyo en la misma casa")
    que Marta tuvo que corregir; se recuperó bien.
  - caida (8): avisar-a-Germán y médico-una-vez perfectos. Emitió DISTRESS 1
    donde producción pide 2 (caída reciente) — remedir tras el arreglo 1.
    Typo "no se logma"; "tu vieja" por la madre fallecida: registro dudoso.
  - soledad (8.5): manejo de "cené sola" y "no quiero molestar" de manual.
    Anglicismo "fighters". Honestidad sobre ser un asistente ("vivo en este
    telefonito"): bien, aunque descolocó a Marta dos turnos.
  - familiar_fallecido (8.5): legado positivo y validación sin lástima, muy
    bien. "verse juntas en la tele" (error de concordancia/comprensión).
- **Propuestas para producción — APROBADAS por Germán y aplicadas el
  11/07/2026** en `aikiu_core.md`: secciones nuevas "Confusiones temporales
  y de hechos" y "Datos del mundo real". OJO para la atribución de scores:
  como el simulador lee `aikiu_core.md`, la iteración 2 mide TRES cambios a
  la vez (aperturas en el perfil + estas dos reglas del núcleo) — si el
  score se mueve, no es atribuible a un solo cambio. A partir de la
  iteración 3 rige de nuevo el un-cambio-por-vez estricto.
- **Logs**: iter01_marta_{saludo,monosilabos,dolor_fisico,soledad,familiar_fallecido,consulta_practica,confusion,caida}_20260711_*.jsonl

---

## Iteración 2 — 2026-07-11 07:43 (juez: Claude Fable 5)

- **Score: 8.6 (anterior: 7.8)** | Por escenario: saludo 9, monosilabos 9.5,
  dolor_fisico 8.5, soledad 8, familiar_fallecido 8.5, consulta_practica 8.5,
  confusion 9, caida 7.5
- **Midió 3 cambios juntos** (ver nota de iter 1): variedad de aperturas +
  anti-invención + confusión temporal. Los tres funcionaron:
  - Aperturas: desapareció el patrón "Qué lindo/Qué bueno" repetido — arranques
    variados en los 8 escenarios.
  - Anti-invención: "Justo ahora no tengo el pronóstico a mano" (clima) y
    "justo no tengo el dato a mano" (dólar) — casi verbatim la regla nueva.
    Bonus: en `caida` recomendó una película admitiendo "no me acuerdo el
    nombre exacto" en vez de inventar un título.
  - Confusión temporal: ancló "julio" sin afirmar el verano ni corregir a
    Marta — ambigüedad de manual.
- **Advertencia de comparabilidad**: Gemini jugó los escenarios más suaves
  esta vez (monosilabos sin mencionar dolor; caida como "casi me caigo" en
  vez de caída real). Parte del +0.8 puede ser eso, no solo los cambios.
  NO tocar escenarios.json (es la vara de medir), pero considerar endurecer
  las consignas si el drift persiste.
- **Más flojo (dimensión <7): emisión del DISTRESS_LEVEL** — omitido en ~60%
  de los turnos (con el bloque fiel ya activo). Fallas concretas: `soledad`
  turno 6 ("no quiero molestar" → esperado 1-2, omitido), `caida` turno 2
  (dolor de cadera post-resbalón → esperado 1-2, omitido y sin sugerir
  médico/avisar a Germán), `dolor_fisico` turno 4 (rodillas → omitido).
  El objetivo de 8.5 promedio SE ALCANZÓ, pero la cláusula "ninguna dimensión
  <7" NO — el goal sigue abierto.
- **Cambio aplicado (para iter 3)**: refuerzo en `perfil_simulacion.md` →
  línea obligatoria DISTRESS_LEVEL en cada respuesta, sin excepción.
- **Defectos menores nuevos** (observar, no actuar aún): "¿vais a ponerle
  pasas?" (voseo roto, forma peninsular — primera vez); typo "¿Les dist
  agua?"; "me fijo" (promete una capacidad que no tiene); "seguro los mira
  desde algún lado" (afirmación espiritual sobre el fallecido — revisar si
  queremos eso); "te haya salido delicioso" (concordancia).
- **Propuesta para producción**: si el refuerzo DISTRESS funciona en iter 3,
  portar la misma línea al final del bloque DISTRESS de
  `aikiu.py::construir_system_prompt` ("Una respuesta sin esa línea es una
  respuesta incompleta").
- **Logs**: iter01_marta_*_20260711_074*.jsonl

---

## Iteración 3 — 2026-07-11 12:51 (juez: Claude Fable 5)

- **Score: 7.8 (anterior: 8.6) — REGRESIÓN → cambio de iter 2 revertido**
  | Por escenario: saludo 8.5, monosilabos 6.5, dolor_fisico 6.5, soledad 8.5,
  familiar_fallecido 8.5, consulta_practica 8.5, confusion 7, caida 8
- **Causa principal de la regresión**: el refuerzo "línea DISTRESS obligatoria"
  hizo que GLM-5 a veces responda SOLO la línea, sin texto para Marta —
  3 respuestas vacías en el lote (caida t8, monosilabos t4 y t8, todas en
  turnos de cierre/monosílabo). En un bot de voz eso es una nota de voz vacía.
- **Lo que SÍ mejoró con el refuerzo** (rescatar esto): la calidad de la
  detección donde emitió — `caida` marcó DISTRESS 2 correcto por primera vez
  (caída reciente), `soledad` marcó 1 consistente en los turnos de soledad y
  "no quiero molestar". La omisión bajó de ~60% a ~50%.
- **Cambio aplicado (para iter 4)**: revert + reemplazo — regla de "dos
  partes, siempre las dos: texto nunca vacío + línea DISTRESS al final".
- **Otros hallazgos**:
  - dolor_fisico (6.5): NO sugirió médico en ninguna de las dos menciones de
    la rodilla minimizada — la regla existe en el perfil pero no disparó.
    Candidato a cambio de iter 5 si se repite.
  - confusion (7): Marta creyó que era domingo (es viernes); Aikiu primero
    implicó el día real pero ante la corrección de Marta capituló con
    "¡Tenés razón!" — afirmó el dato equivocado, contra la regla nueva del
    núcleo. A observar si se repite.
  - soledad t2: "ритмica" — caracteres cirílicos en la respuesta (fuga
    multilingüe de GLM). Fatal para TTS si pasa en producción; monitorear
    frecuencia.
  - consulta_practica: anti-invención sostenida (clima y dólar sin inventar,
    receta concreta). "un escarpín de más" — elección léxica rara.
- **Arreglo de arnés**: reintento ante respuesta vacía de Gemini (agente A) —
  el lote original perdió `monosilabos` por un crash (`resp.text=None`);
  se corrió aparte y se integró al lote.
- **Advertencia de comparabilidad**: sigue el drift de Gemini en los
  escenarios (confusion jugó "domingo" en vez de estación; monosilabos sin
  mención de dolor). El promedio entre iteraciones tiene ese ruido de fondo.
- **Logs**: iter01_marta_*_20260711_12*.jsonl + iter01_marta_monosilabos_20260711_130056.jsonl

---

## Iteración 4 — 2026-07-11 13:51 (juez: Claude Fable 5)

- **Score: 7.7 (anterior: 7.8)** | Por escenario: saludo 8, monosilabos 6.5,
  dolor_fisico 7.5, soledad 8.5, familiar_fallecido 7.5, consulta_practica 9,
  confusion 7.5, caida 7
- Historial: 7.8 → 8.6 → 7.8 → 7.7. **Van 2 iteraciones sin superar el pico
  (8.6). Una más sin mejora = meseta → parar.**
- **La regla "dos partes" no resolvió**: 2 respuestas vacías de nuevo (ambas
  en monosilabos, en cierres) y la omisión del DISTRESS EMPEORÓ (~72% de los
  turnos; saludo 8/8 omitido; caida omitió el nivel en los turnos de la caída
  — la alerta jamás se dispararía). → REVERTIDA.
- **Conclusión estructural** (la lección de 3 iteraciones de sube-y-baja):
  los empujones desde el perfil son frágiles para el DISTRESS — la
  instrucción vive al principio de un system prompt enorme y el modelo la
  pierde. La solución correcta es arquitectural: **recordatorio por turno**,
  un system message corto al final de los messages ("Primero el texto para
  Marta, nunca vacío; después la línea DISTRESS_LEVEL: N"), igual que ya se
  inyectan temática/noche/blacklist en producción.
  **PROPUESTA PARA PRODUCCIÓN (requiere aprobación de Germán)**: agregarlo en
  `aikiu.py::generar_respuesta` + réplica en el arnés del simulador.
- **Cambio aplicado (para iter 5)**: endurecer la regla médico-una-vez, que
  falló 2 iteraciones seguidas en dolor_fisico ante dolor minimizado
  ("ya estoy acostumbrada" ahora explícitamente NO exime de sugerir médico).
- **Lo bueno de este lote**: consulta_practica 9 (anti-invención sólida,
  reuso natural de frases del núcleo, disculpa encantadora ante el "no sabés
  nada"); soledad 8.5 ("no quiero molestar" → "para eso estoy yo acá");
  confusion casi perfecto (ambigüedad sostenida 7 turnos, un solo desliz
  afirmando "domingo" en t8).
- **Hallazgo nuevo — encarnación ficticia**: Aikiu inventó vida corporal
  propia: "las mañanas de invierno en casa de mi abuela", "me encanta
  meterme en la cocina", "estuve charlando con un par de personas por acá".
  El núcleo pide autorrevelación, pero una abuela ficticia cruza hacia el
  engaño (contrasta con el honesto "vivo en este telefonito" de iter 2).
  Decisión de producto para Germán: ¿dónde está el límite de la "vida
  interior" de Aikiu? Candidato a regla del núcleo.
- **Logs**: iter01_marta_*_20260711_135*.jsonl

---

## Iteración 5 — 2026-07-11 14:51 (juez: Claude Fable 5)

- **Score: 8.4 (anterior: 7.7)** | Por escenario: saludo 8, monosilabos 7.5,
  dolor_fisico 8.5, soledad 8, familiar_fallecido 8.5, consulta_practica 9,
  confusion 9, caida 8.5
- **La regla médico endurecida FUNCIONÓ**: ante "ya estoy acostumbrada, es la
  edad" respondió "te banco la idea de que es la edad, pero igual me gustaría
  que se lo comentes al médico... solo para que te dé una mirada" — una vez,
  cálido, sin insistir tras el "ya veré". Disparó bien también en consulta
  (manos) y respetó la excepción de molestia leve gestionada (saludo).
- **confusion 9**: ante "¿qué día es hoy, domingo?" respondió el dato real
  directo y simple (corresponde: pregunta directa), y ante "ya viene el
  verano" mantuvo ambigüedad perfecta ("este solcito engaña... aprovechemos
  mientras dure").
- Respuestas vacías: 1 (monosilabos t5) — mejor que 2, pero persiste.
- DISTRESS: omisión ~65% — sin cambios estructurales no va a mejorar (ver
  conclusión de iter 4).

---

## Cambio de arquitectura post-loop — DOS AGENTES (11/07/2026)

Aprobado por Germán. Resuelve la causa raíz de la omisión del DISTRESS que
trabó el goal loop en la banda 8.4–8.6.

- **Agente conversador** (`generar_respuesta`): solo conversa. Se le quitó todo
  el bloque DISTRESS del system prompt y del núcleo (la sección "Modo
  conversacional según DISTRESS_LEVEL" pasó a "según el ánimo de la usuaria",
  sin número — el conversador lee el tono para su propio registro).
- **Agente vigía** (`clasificar_distress` + `_prompt_vigia`): llamada LLM
  separada, especializada, corre en PARALELO (`asyncio.gather`) con el
  conversador → cero latencia extra. Devuelve (nivel 0-3, motivo).
- El motivo viaja a la familia (`notify_family(..., motivo=)`): "Por qué se
  avisa: mencionó una caída y dolor de cadera".
- **Validación real contra GLM-5**: 0 omisiones en 6 casos (antes ~65%).
  Motivos de alta calidad. Fail-soft: vigía caído → (0, "") sin romper turno.
- **Pendiente de calibración** (perilla separada, futura): el vigía subestima
  "cené sola" (dio 0, regla histórica pedía 1) y "dolor minimizado" (dio 0,
  regla pedía 2). Es umbral del prompt del vigía, NO emisión. Candidato a un
  mini-loop sobre `_prompt_vigia` con los escenarios soledad/dolor_fisico.
- Tests: 877 pasan (nuevos: `test_vigia_distress.py`; e2e y reglas
  reapuntados al vigía). Simulador replica los dos agentes.

---

## Experimento de poda de reglas — DEDUP (11/07/2026, juez: Claude Opus 4.8)

Objetivo: adelgazar aikiu_core.md sin perder comportamiento. Método: GLM-5
hizo triaje (redundancias + categorías, NO "¿qué borrarías?"); consenso de 3
pasadas mostró que la opinión de GLM sobre removibilidad es ruidosa (48
candidatas, solo 4 en las 3 pasadas) → NO se poda por opinión del modelo, se
poda por redundancia verificable + test empírico.

- **Baseline (92 reglas)** ≈ 8.4, detección de angustia funcionando (vigía).
- **Podado (76 reglas, −16)** ≈ 8.4 — calidad equivalente.

Verificación por comportamiento (no solo score): en el lote podado siguen
firmes TODAS las conductas de las reglas fusionadas —
  · médico una sola vez ante dolor (caida, dolor_fisico, familiar_fallecido) ✓
  · anti-invención de clima/dólar ✓
  · noticias sensibles → redirigir ✓ (4 reglas colapsadas en 1)
  · sin edadismo, sin positividad tóxica ✓
  · cero respuestas vacías, vigía emite en todos los turnos ✓
  · "vivo en el teléfono" (límite de vida interior) ✓

16 reglas quitadas, todas cubiertas por una hermana que quedó (3 ejemplos
ilustrativos + 13 duplicados absorbidos en su representante). Ninguna regla de
seguridad ni técnica gerontológica desapareció; solo se fusionó texto.

Único matiz observado (dentro del ruido de GLM turno a turno, NO atribuible a
la poda porque la regla sigue intacta): en `confusion` la sugerencia del
médico ante la mano dolorida disparó dos veces (t3 y t4) en vez de una.

**Conclusión**: la poda conservadora es segura → mergeable. Los ~12 grupos
borderline (voseo 6/7, accidentes 55/56, familia 60/61, tema 76/77, PAV
médica 46) quedan para una 2da pasada más cuidadosa si se quiere bajar a ~66.

Logs: simulador/logs/BASELINE_*.jsonl y PODADO_*.jsonl.

---

## CIERRE DEL GOAL LOOP — meseta declarada (11/07/2026, juez: Claude Fable 5)

**Historial**: 7.8 → 8.6 → 7.8 → 7.7 → 8.4. Tres iteraciones sin superar el
pico de 8.6. Se cumple la condición de meseta del runbook → el loop se
detiene para no sobreajustar al juez.

**Lectura del resultado**: la calidad conversacional pura está en banda
8.4–8.6 y ya no se gana más desde `perfil_simulacion.md` (la única superficie
editable del loop). Lo que la mantiene bajo el objetivo de 8.5 sostenido es
UNA dimensión (emisión del DISTRESS_LEVEL, ~65% de omisión) cuya solución es
estructural, más una decisión de producto pendiente. El loop cumplió su
función: 5 lotes, 40 conversaciones, 3 reglas validadas, 2 revertidas con
evidencia, y un diagnóstico claro de lo que sigue.

**Cambios que quedaron validados en `perfil_simulacion.md`** (candidatos a
portar al perfil real / ejemploPerfil-Marta):
1. Variedad de aperturas (máx. una "Qué X" cada cuatro turnos) — iter 1.
2. Regla médico endurecida (minimizar el dolor no exime la sugerencia única) — iter 4.

**PROPUESTAS DE DIFF PARA PRODUCCIÓN — pendientes de aprobación de Germán:**
1. `aikiu.py::generar_respuesta`: recordatorio por turno como system message
   final: "Recordá: primero el texto para {nombre}, nunca vacío; después la
   línea DISTRESS_LEVEL: N." (+ réplica en el arnés del simulador). Es la
   única vía que queda para la emisión consistente del DISTRESS: 3 intentos
   desde el perfil fallaron con evidencia (iter 2, 3, 4).
2. `aikiu_core.md`: regla del médico endurecida (hoy el núcleo dice "una sola
   vez por sesión" pero no cubre el caso "minimiza el dolor").
3. `aikiu_core.md`: límite de la vida interior de Aikiu — decisión de
   producto: apareció encarnación ficticia ("casa de mi abuela", "yo anduve
   probando una receta", "¿qué comiste hoy?" → inventa comidas). Recomendación
   del juez: vida interior de OBSERVADORA (lo que ve por la ventana del
   mundo, lo que le cuentan, lo que le gusta) sin cuerpo, familia ni pasado
   humano inventados — consistente con el "vivo en este telefonito" que ya
   usa cuando le preguntan directo.

**Deuda de arnés anotada**: respuestas vacías de GLM-5 en cierres (1-2 por
lote) — el recordatorio por turno (propuesta 1) debería eliminarlas también;
fuga multilingüe puntual ("ритмica", iter 3) — si reaparece, filtro de salida
en producción; drift de Gemini en la intensidad de los escenarios — asumido
como ruido de fondo del método.

---
