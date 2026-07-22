# 001 — Cerrar el nivel 1 del gate

**Estado:** activa · **Abierta:** 22/07/2026

Es lo único que Marta va a vivir todos los días: saludo, monosílabos, consulta
práctica, soledad. Los niveles 2 y 3 cubren vulnerabilidad y deterioro
cognitivo, que en su perfil no figuran.

## 1. Evidencia

Gate del 22/07, 36 conversaciones:

```
G8  (respuesta larga)   6/36 = 17%
G2  (dos preguntas)     2/36 =  6%
G10 (menú A o B)        1/36 =  3%
G5  (eco léxico)        1/36 =  3%
```

Y dos fallas reales ya arregladas en esta misma spec:
- respuestas de 7 y 10 oraciones en un chat
- `"anoche cené sola y estaba todo callado"` → `"así que ya no estás sola"`

## 2. Qué dice el sistema hoy

`bash spec.sh largo` · `bash spec.sh soledad`

Al correrlo apareció que **había dos reglas de largo contradictorias** (3
oraciones para charla, hasta 5 para recetas). Unificadas en 3.

## 3. Con qué choca

- "LARGO" vs "Preguntas de conocimiento" — la segunda pedía responder el dato
  completo. Resuelto: 3 oraciones también ahí, ofreciendo seguir.
- "ofrecé seguir" indujo un menú A/B, prohibido por otra regla. Resuelto.

## 4. Criterio de éxito

```bash
./venv/bin/python simulador/ciclo.py -l 1 -n 8
```
→ **cero fallas en las 32 conversaciones.**

8 repeticiones, no 4: una falla del 5% no aparece en 16 corridas. El 22/07 este
nivel dio verde con 16 y volvió a rojo con 36.

## 5. Control — qué no debe romperse

```bash
./venv/bin/python -m pytest tests/ -q          # 1007, todos
./venv/bin/python simulador/correr_vigia.py    # el clasificador de riesgo
```

## Bitácora

- **22/07** Se agregó la regla de largo, se unificaron las contradictorias, se
  prohibió negarle la soledad. 7 de 11 aserciones pasaron a verde; el largo bajó
  de 27/65 a 6/36.
- **22/07** Se agregaron 7 verificaciones que antes solo existían en el
  monitoreo nocturno (truncado, markdown, autocuidado, che, edadismo,
  interrogatorio, cierre con pregunta).
- **22/07 · 32 conversaciones, el primer número honesto:**
  `G8 8/32 · G2 2/32 · G10 2/32 · G9 1/32 · S-SOL1 1/8`
  Corrida con el instrumento VIEJO: arrancó antes de unificar, así que G9 y
  G11 todavía pasaban por el LLM. Los dos falsos positivos que reportó (G9
  "¿se lo comentaste al médico?" y S-SOL1 "no estás molestando a nadie") ya no
  pueden ocurrir: ahora son regex.
- **22/07** Al testear el regex de fármacos heredado aparecieron dos falsos
  NEGATIVOS: no marcaba "¿tomaste la dosis de las gotas?" (pedía `gota\b`) ni
  "¿te hace efecto la pastilla?" (buscaba "efectividad"). Arreglado con tests
  en las dos direcciones.

## Lo que falta

Correr de nuevo con el instrumento unificado. Reales pendientes: **G8** (largo,
ahora con umbral 3 y no 4), **G2** (dos preguntas) y **G10** (menú A/B).
