# 005 — WhatsApp para el MVP (el canal real de Marta)

**Estado:** backlog, prioridad ALTA · Abierta 25/07/2026

## La decisión

Aikiu se mueve a WhatsApp. No es una optimización: es el canal donde la única
usuaria que importa ya vive.

## Por qué (el razonamiento, para no re-litigarlo)

- **Marta usa WhatsApp todo el tiempo.** Tiene 83 años; Telegram tendría que
  instalarlo y aprenderlo, sin ningún motivo social para abrirlo. La barrera
  más grande al norte —abrir una app desconocida— desaparece en WhatsApp.
- **Los testers de Telegram no eran señal.** Cata (23) y Nico (amigo) no
  engancharon, pero nunca fueron proxies de Marta: no tienen la necesidad que
  Aikiu resuelve. Su abandono era esperable y no dice nada sobre Marta. Parte
  de la fricción, además, fue tener que instalar Telegram.
- **Sin instalar nada, Irene puede testear ya.** Se le pasa el número y listo.
  Eso destraba la beta con una persona representativa, sin la fricción que
  probablemente tumbó a los anteriores.

**Reencuadre incómodo:** veníamos puliendo la conversación (que ya es buena)
cuando el cuello de botella real al norte quizás era la plataforma. El único
test que vale es Marta, y Marta está en WhatsApp.

## Cómo — MVP con librería no oficial (Baileys), número dedicado

Descartado para el MVP: API oficial de Meta (semanas de verificación) y BSPs
tipo Twilio (siguen con ventana de 24h + plantillas, que chocan con el saludo
matutino proactivo).

Elegido: **Baileys** (o whatsapp-web.js) — maneja una cuenta real por el
protocolo de WhatsApp Web (QR). Ventajas decisivas para el MVP:
- cero verificación de Meta, testeable en horas
- **sin ventana de 24h ni plantillas**: el saludo proactivo funciona libre
- costo ~$0
- el cerebro Python NO se toca: un puente Node reenvía a aikiu por HTTP, igual
  que hoy la capa de Telegram (~77 líneas de I/O de 2708 de lógica)

**Costo real:** viola los ToS de WhatsApp; Meta puede banear el número. Se
contiene con un **número dedicado** (SIM barata / segundo número): si banean,
Marta no pierde nada —su WhatsApp personal está intacto— y se saca número
nuevo. El riesgo pasa de grave a molesto. Es reverse-engineering: se rompe
cuando WhatsApp actualiza; aceptable para un MVP de un usuario.

## Plan

1. Número dedicado para Aikiu (SIM o segundo número).
2. Puente Node con Baileys: recibe mensajes → POST al backend Python →
   respuesta → envía. Voz: WhatsApp manda notas de voz, ya tenemos Whisper.
3. Backend Python sin cambios de cerebro; adaptar la capa de I/O (los ~18
   puntos de envío y el router de entrada).
4. Irene testea. Después Marta.
5. Telegram queda de fallback, no se tira.

## Camino serio a futuro (post-validación)

API oficial de Meta cuando haya que escalar (más usuarios, sin riesgo de ban).
El saludo matutino sería la única plantilla a pre-aprobar; el resto, texto
libre dentro de la ventana que abre Marta al responder.

## Preguntas abiertas

- ¿Irene usa WhatsApp? (casi seguro sí — ese es el punto)
- ¿El saludo matutino proactivo es el gancho, o alcanza con que Marta inicie?
  Con Baileys da igual (todo es libre), pero define el diseño si algún día se
  pasa a la API oficial.
- Puente en Node vs. binding Python (neonize/whatsmeow). Node/Baileys es el
  más maduro; el puente HTTP mantiene el cerebro intacto.
