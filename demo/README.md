# Demo visual

Demo animado del flujo de mensaje-puente, fiel a lo que hace el código.

## Cómo verlo

Abrí [`index.html`](./index.html) en cualquier navegador moderno. El demo arranca solo.

- **Click**: reinicia desde el principio.
- **Espacio**: pausa / reanuda.
- **Formato**: vertical 9:16, pensado para grabar y subir a Reels / TikTok / Stories.

## Storyboard (8 escenas, ~40 s)

| # | Escena | Duración | Lo que muestra |
|---|---|---|---|
| 0 | Intro | 3.2 s | Logo `aikiu` + tagline |
| 1 | El hijo | 5.2 s | Germán abre el bot familiar (`Aikiu · familiar`) y manda `/mensaje` |
| 2 | Aikiu responde | 4.2 s | Bot pide: *"Enviá tu mensaje para Rosa (texto o nota de voz)"* |
| 3 | El audio | 5.5 s | Germán graba: *"¿Cómo amaneciste, ma? Acordate de los remedios. Te quiero."* |
| 4 | Entregado | 5.2 s | Bot confirma: *"Listo, le mandé a Rosa..."* |
| 5 | Transición | 2.4 s | *Mientras tanto...* |
| 6 | La abuela | 5.8 s | Rosa recibe la nota de voz con la voz de Aikiu |
| 7 | Mensaje emocional | 4.2 s | *Sabés que está bien.* |
| 8 | Outro / CTA | 5.0 s | Logo + `github.com/geermaanv/aikiu` |

## Fidelidad al código

Los strings del bot son **exactamente** los del código fuente:

| Texto en el demo | Origen en el código |
|---|---|
| `"Hola Germán, ya estabas registrado."` | `familiar_bot.py:153` |
| `"Enviá tu mensaje para Rosa (texto o nota de voz). /cancelar para salir."` | `familiar_bot.py:290` |
| `"Germán te manda a decir: ..."` | `familiar_bot.py:331` |
| `"Listo, le mandé a Rosa: ..."` | `familiar_bot.py:344` |
| `"Buenos días Rosa, soy Aikiu. Hoy en Olivos hay X grados. ¿Cómo amaneciste hoy?"` | `aikiu.py:451` (`saludo_matutino`) |

Nombres usados (todos vienen del repo):

- **Rosa** — adulto mayor (hardcoded en strings del bot familiar)
- **Aikiu** — asistente (`config.yml::nombre_asistente`)
- **Germán** — hijo (`perfil.md`, sección Familia)
- **Olivos** — ciudad (`config.yml::ciudad`)

## Convertirlo a video MP4

Si querés subirlo a Instagram/TikTok como video, hay dos formas fáciles:

1. **Captura de pantalla del navegador** (Mac: `Cmd+Shift+5` → grabar área; Windows: app *Recorte* o `Win+G` Game Bar; Linux: `kazam`/`OBS`).
2. **Extensión gratuita**: *Loom*, *Screencastify* o el grabador integrado de Chrome DevTools (`Cmd+Shift+P` → "Start screenshot recording" en algunos).

Recomendado: ventana del navegador en aspect 9:16 (achicá el ancho hasta que el viewport quede vertical sin bandas negras).
