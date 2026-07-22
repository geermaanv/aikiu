# 002 — Que las conversaciones reales se conviertan en casos

**Estado:** backlog · **Abierta:** 22/07/2026

## El problema

Un tester con cuatro mensajes destapó más fallas que cuarenta conversaciones
simuladas — no por ser humano, sino porque trajo situaciones que no estaban en
la lista. Hoy esas conversaciones se leen una vez y se pierden.

`core/calidad.py` ya corre cada noche sobre las charlas reales y ahora avisa al
bot admin. Falta el paso siguiente: que un hallazgo confirmado se convierta en
un **caso permanente** que el gate verifique para siempre.

## Por qué importa

Lo que mejora de forma monótona no es el modelo ni el prompt: es el banco de
casos, que solo crece. Cada falla descubierta una vez queda atrapada.

## Criterio de éxito (a definir al activarla)

Un hallazgo del monitoreo nocturno se puede promover a caso con un comando, y
al correr el gate aparece verificándose.

## Nota

El humano queda en un solo lugar —confirmar si un hallazgo es real— y por eso
el trabajo manual no crece con el volumen de conversaciones.
