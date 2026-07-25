# 004 — Evaluar DeepSeek v3.2 como conversador (post-Marta)

**Estado:** backlog · **NO antes del despliegue con Marta**

## Por qué está acá

GLM-5 no cachea en OpenRouter (probado el 25/07: `cached_tokens=0` en llamada
idéntica, aunque la tarifa anuncie caché). Cada turno del gate manda ~7500
tokens sin descuento, y eso hace caras las corridas.

DeepSeek v3.2: **~5x más barato** que GLM-5 ($0.27/$0.40 vs $0.95/$2.55 por M)
**y cachea de verdad** (caché automático). En papel, un golazo de costo.

## Por qué NO ahora

1. El caché ahorra en el TESTEO, no con Marta: su volumen real (~5-10
   charlas/día) cuesta centavos con cualquier modelo. Elegir el conversador por
   el costo de las pruebas es al revés.
2. Cambiar el conversador = revalidar TODO el núcleo. Las 199 líneas de reglas
   están calibradas contra las mañas de GLM-5. Otro modelo reabre toda la
   calibración justo antes del despliegue.
3. GLM-5 se eligió por su rioplatense ("fase GLM" en la memoria del proyecto).

## Cómo evaluarlo cuando toque

El simulador ya tiene el override: `SIM_BOT_MODEL="openrouter:deepseek/deepseek-v3.2"`.
Correr el gate completo con DeepSeek y comparar contra GLM-5, mismas aserciones.
Si convierte igual de bien en rioplatense, el ahorro de 5x sí mueve la aguja —
con datos reales de uso de por medio, no antes.
