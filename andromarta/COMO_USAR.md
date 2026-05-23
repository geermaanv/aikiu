# Cómo usar Andromarta — guía paso a paso

Andromarta es una "abuela falsa" hecha con inteligencia artificial. Vive en una cuenta de Telegram propia y se hace pasar por una persona mayor real chateando con Aikiu. Sirve para probar Aikiu sin tener que molestar a la persona mayor real.

Esta guía te lleva desde cero hasta verla conversar.

---

## Antes de empezar — lo que tenés que tener

1. **Aikiu instalado y andando** en alguna computadora (esta misma o un servidor).
2. **Un número de celular para la cuenta sintética**. Lo ideal es que sea **un número aparte** (no el tuyo personal ni el de la persona mayor). Puede ser:
   - una SIM o eSIM nueva,
   - un chip viejo que tengas guardado,
   - un servicio online que te dé un número que recibe SMS.

   **¿No tenés otro número?** Podés usar el tuyo personal con algunos recaudos. Ver la sección [Si vas a usar tu propio número](#si-vas-a-usar-tu-propio-número) más abajo.
3. **Acceso al celular** durante 5 minutos para recibir un código por SMS la primera vez.
4. **Un bot de Telegram aparte** para que Andromarta le hable. **NO** uses el bot del adulto mayor real, porque la primera vez que Andromarta le mande un mensaje el bot la va a registrar como "su" persona mayor y se rompe todo.

Tiempo total: alrededor de 15 minutos la primera vez.

---

## Si vas a usar tu propio número

Si en `ANDROMARTA_PHONE` ponés **tu número personal** (el que ya usás todos los días en Telegram), el sistema funciona igual, pero hay cosas que tenés que saber y cuidados que tenés que tomar.

### Lo que vas a ver

- En Telegram tenés un solo perfil con tu nombre. Cuando Andromarta le hable al bot de prueba, los mensajes van a aparecer firmados con **tu nombre**, igual que cuando le hablás vos a cualquier persona. Si alguien mira por arriba de tu hombro, va a ver "vos" charlando con un bot.
- Lo mismo con las notas de voz: van a salir desde tu cuenta, no desde una identidad sintética separada.

### Cuidados importantes

1. **No le hables al bot de prueba a mano mientras Andromarta corre.** Si vos también le tipeás algo al mismo bot, ese mensaje le va a llegar a Aikiu como si fuera de Andromarta (porque para Telegram los dos vienen del mismo chat). Vas a ver que las respuestas se mezclan y se hace un quilombo. Si querés probar algo vos a mano, primero parás Andromarta (`Ctrl + C` en la terminal donde corre) y después relanzás.

2. **El archivo de sesión es sensible.** Cuando Andromarta arranca por primera vez crea `andromarta/data/andromarta.session`. **Ese archivo "es" tu cuenta de Telegram**: cualquiera que lo copie puede leer y mandar mensajes desde tu cuenta (a cualquier chat, no solo al bot de prueba). Si la computadora es solo tuya, no hay problema. Si la compartís o vas a subir el proyecto a un servidor compartido, considerá:
   - Borrarlo cuando termines de testear: `andromarta/data/andromarta.session` (y `andromarta.session-journal`). La próxima vez vas a tener que loguearte de nuevo con el código de Telegram.
   - Verificar que `andromarta/data/` esté en `.gitignore` (ya lo está, pero no está de más confirmar).

3. **Revisá las sesiones activas cada tanto.** En Telegram → **Configuración → Privacidad y seguridad → Dispositivos** (en celular) o **Settings → Active Sessions** (en Desktop). Vas a ver una sesión que dice "andromarta" o el nombre que pusiste en my.telegram.org. Si en algún momento sospechás algo raro, podés desconectarla de ahí con un click.

4. **Lo del bot de prueba sigue valiendo.** Aunque uses tu propio número, **NO** apuntes `ANDROMARTA_AIKIU_USERNAME` al bot del adulto mayor real. Tiene que ser un bot de Aikiu de prueba creado solo para esto. Es la regla más importante.

5. **El `CHAT_ID` en el `.env` de Aikiu coincide con vos.** Como Andromarta habla desde tu propia cuenta de Telegram, su chat_id es el mismo que el tuyo. Aikiu ya te tiene autorizado, así que no hace falta cambiar nada en el `.env` raíz por este lado. Pero acordate: si más adelante reseteás `state.json` o cambiás el `CHAT_ID`, Andromarta lo va a notar y va a dejar de funcionar hasta que vuelvas a alinear.

### Resumen

Es perfectamente válido usar tu propio número. La mayoría de la gente que prueba Andromarta lo hace así porque no quiere comprar otra SIM solo para esto. Solo tenés que ser consciente de los cuatro puntos de arriba y vas a estar bien.

---

## Paso 1 — Conseguir las llaves de Telegram

Esto se hace una sola vez por cuenta. Son dos códigos que Telegram te da para que un programa pueda usar la cuenta.

1. Entrá a [https://my.telegram.org](https://my.telegram.org) **desde una computadora**.
2. Te va a pedir el número de celular sintético (con código de país, por ejemplo `+5491138...`).
3. Te va a llegar un mensaje a Telegram (no SMS) con un código. Ponelo.
4. Una vez adentro, hacé clic en **"API development tools"**.
5. Te aparece un formulario. Llenalo así:
   - **App title**: `andromarta` (o lo que quieras).
   - **Short name**: `andromarta`.
   - **Platform**: elegí "Other" o "Desktop".
   - El resto dejalo vacío.
6. Apretá **"Create application"**.
7. La pantalla te muestra dos cosas:
   - **App api_id**: un número, por ejemplo `12345678`.
   - **App api_hash**: una cadena larga de letras y números.
8. **Copialos a un papel o documento privado**. Los vas a necesitar en el paso 4.

> Nunca compartas el `api_hash`. Es como una contraseña.

---

## Paso 2 — Crear un bot Aikiu de prueba

Andromarta tiene que hablarle a un bot Aikiu, pero **no al de la persona mayor real**. Creamos uno nuevo solo para pruebas.

1. Abrí Telegram con tu cuenta personal (la tuya, no la sintética).
2. Buscá `@BotFather` y abrí el chat.
3. Mandale `/newbot`.
4. Te pide un nombre (cualquiera, por ejemplo `Aikiu Pruebas`).
5. Te pide un username único, que tiene que terminar en `bot`. Probá algo como `aikiu_test_TUNOMBRE_bot`.
6. Si lo acepta, te devuelve un mensaje con un **token**: una cadena larga del estilo `1234567890:AAH...`.
7. **Copiá ese token a un papel.** Es lo que va a usar Aikiu de prueba para conectarse.
8. Anotate también el **username** del bot (el que termina en `bot`, sin la arroba).

Ahora hay que decirle a Aikiu que use ese bot de prueba. Editá el archivo `.env` en la **raíz del proyecto** (NO el de andromarta) y reemplazá el `BOT_TOKEN` por el token nuevo. Después reiniciá Aikiu.

---

## Paso 3 — Hacer que la cuenta sintética y el bot se conozcan

Andromarta no puede empezar a hablarle al bot de la nada: Telegram exige que ambos lados se hayan saludado al menos una vez.

1. En el celular sintético (o en Telegram Desktop logueado con la cuenta sintética), buscá el bot que creaste en el paso 2 por su username.
2. Abrí el chat y mandale `/start`.
3. Aikiu debería contestarte. Si no contesta, revisá que Aikiu esté corriendo y apuntando al bot nuevo.

Listo, las dos puntas se conocen.

---

## Paso 4 — Configurar Andromarta

Andromarta tiene su propio archivo de configuración separado, dentro de la carpeta `andromarta/`.

1. Abrí la carpeta `andromarta/` del proyecto en el explorador de archivos.
2. Vas a ver un archivo llamado `.env.example`. Hacé una **copia** y renombrala como `.env` (sin "example", solo `.env`).
3. Abrí `.env` con el bloc de notas o cualquier editor de texto.
4. Llenalo con los datos que conseguiste antes:

```
GROQ_API_KEY=la_misma_key_que_usa_aikiu

ANDROMARTA_API_ID=12345678
ANDROMARTA_API_HASH=tu_api_hash_largo_de_letras_y_numeros
ANDROMARTA_PHONE=+5491138...
ANDROMARTA_AIKIU_USERNAME=aikiu_test_TUNOMBRE_bot
ANDROMARTA_NOMBRE_CLARA=Clara
ANDROMARTA_MODELO=llama-3.3-70b-versatile
ANDROMARTA_VOZ_TTS=es-AR-ElenaNeural
ANDROMARTA_VOZ_PROB=0.4
ANDROMARTA_RITMO_HUMANO=0
ANDROMARTA_MAX_TURNOS_CICLO=15
```

Detalles:

- **`GROQ_API_KEY`**: la misma que usa Aikiu (está en el `.env` raíz del proyecto). Copiala tal cual.
- **`ANDROMARTA_PHONE`**: el número del celular sintético, con el `+` y el código de país. Ejemplo: `+5491138271234`.
- **`ANDROMARTA_AIKIU_USERNAME`**: el username del bot de prueba que creaste, **sin la arroba**.
- **`ANDROMARTA_VOZ_PROB`**: probabilidad de que Andromarta responda con audio en vez de texto. `0` = solo texto. `1` = solo audio. `0.4` = más o menos 4 de cada 10.
- **`ANDROMARTA_RITMO_HUMANO`**: `0` (default) hace que Andromarta responda al toque, sin esperas de "lectura" ni de "tipeo". Poné `1` si querés que simule los tiempos de una persona mayor real (pausa antes de leer, tipeo lento, demora antes de grabar la nota de voz).
- **`ANDROMARTA_MAX_TURNOS_CICLO`**: cuántos mensajes en total (sumando los de Clara y los de Andromarta) puede tener una "conversación" antes de que Andromarta se despida y se calle. Default: `15`. Después de la despedida, queda esperando a que el scheduler decida volver a arrancar otra conversación (ver más abajo).

Guardá el archivo y cerralo.

---

## Paso 5 — Arrancar Andromarta

1. Abrí una terminal (en Windows: PowerShell; en Mac/Linux: Terminal) en la carpeta del proyecto.
2. Activá el entorno de Python (si Aikiu te lo pidió cuando lo instalaste, hacé lo mismo):
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
3. Ejecutá:

```
python andromarta/bot.py
```

**La primera vez:**

- Telegram te va a mandar un código por SMS (o por la app de Telegram en otro dispositivo) al celular sintético.
- Cuando la terminal te lo pida, escribilo y dale enter.
- Si la cuenta sintética tiene contraseña de dos pasos, también te la va a pedir.

Después de eso, Andromarta queda autenticada para siempre (mientras no borres el archivo `andromarta/data/andromarta.session`).

Cuando todo está bien, en la terminal vas a ver mensajes parecidos a:

```
Andromarta arrancando — chateará con @aikiu_test_...
Sesión de Telegram lista.
Bot Aikiu resuelto: id=...
Escuchando mensajes de @aikiu_test_...
```

Si llegaste a ese mensaje, ya está funcionando.

---

## Paso 6 — Mirar la conversación

Para espiar lo que Andromarta y Aikiu se dicen:

1. Abrí Telegram en otro dispositivo (celular o computadora) **logueado con la cuenta sintética**.
2. Buscá el chat con el bot de prueba.
3. Vas a ver los mensajes en tiempo real, igual que una conversación normal de WhatsApp: globos de texto, audios, "escribiendo...", todo.

A veces Andromarta arranca la conversación sola, a veces espera que Aikiu le hable primero. Si no pasa nada en mucho rato, mandale un mensaje vos desde el bot (o desde Aikiu) y va a contestar. Más abajo está la sección [Tiempos, esperas y ritmo de conversación](#tiempos-esperas-y-ritmo-de-conversación) que explica exactamente cuándo Andromarta hace qué y cómo cambiarlo a tu gusto.

---

## Tiempos, esperas y ritmo de conversación

Andromarta tiene cuatro tipos de "tiempo" que podés ajustar. Los más comunes se cambian en `andromarta/.env` (con solo abrir el archivo con un editor de texto y guardar). Los menos comunes están en dos archivos de código (`andromarta/scheduler.py` y `andromarta/estado.py`); también se editan con bloc de notas, son solo dos líneas con números.

> **Después de cambiar cualquiera de estos valores, reiniciá Andromarta** (Ctrl + C en la terminal y volvé a lanzarla). El bot los lee al arrancar; no toma los cambios en caliente.

### 1. Velocidad con la que responde a cada mensaje

Controlado por: **`ANDROMARTA_RITMO_HUMANO`** (en `andromarta/.env`). Default: `0`.

| Valor | Qué pasa |
|---|---|
| `0` (default) | Sin esperas artificiales. Andromarta contesta lo más rápido que Groq genere el texto (típicamente 1–3 segundos). El indicador "escribiendo…" / "grabando audio…" sigue apareciendo, pero solo el tiempo que tarda el procesamiento real. |
| `1` | Simula a una persona mayor real. Espera un rato para "leer" el mensaje, después tipea lento como adulto mayor en WhatsApp, y si responde con audio se demora un poco antes de "grabar". |

Cuando `ANDROMARTA_RITMO_HUMANO=1`, las pausas que aplica son:

| Pausa | Cuándo | Cuánto dura |
|---|---|---|
| Lectura | Antes de empezar a responder | 1,5 s base + hasta 8 s extra según el largo del mensaje recibido (cuanto más largo, más tarda en "leer") |
| Tipeo | Mientras "escribe" el texto, antes de mandarlo | Aprox. `largo / 3` segundos (~3 caracteres por segundo, como adulto mayor), con un mínimo de 2 s y un máximo de 20 s |
| Grabación | Antes de enviar una nota de voz | Entre 2 y 5 s al azar |

Estos números están hardcodeados en `andromarta/bot.py` (funciones `_pausa_lectura`, `_pausa_tipeo`, `_pausa_grabacion`); si querés afinarlos podés editarlos a mano, pero la mayoría de la gente solo necesita el on/off.

### 2. Largo de cada conversación (corte por cantidad de mensajes)

Controlado por: **`ANDROMARTA_MAX_TURNOS_CICLO`** (en `andromarta/.env`). Default: `15`.

Cada "conversación" tiene un tope de mensajes **contando los de Clara y los de Andromarta juntos**. Cuando la respuesta de Andromarta sería la que llega al tope, manda una despedida natural (algo como "bueno mi vida, te dejo que voy a poner la pava, hablamos más tarde") y queda en silencio: si Clara le sigue escribiendo, **no contesta**. La única manera de reabrir es que el sorteo de iniciativa decida arrancar una conversación nueva (ver punto 3).

| Si ponés... | Pasa esto |
|---|---|
| `ANDROMARTA_MAX_TURNOS_CICLO=15` (default) | Conversaciones de ~7 idas y vueltas antes del cierre |
| Más bajo (ej. `8`) | Conversaciones más cortas, Andromarta se despide antes |
| Más alto (ej. `30`) | Conversaciones más largas |
| `2` (mínimo permitido) | Andromarta responde un solo mensaje y ya se despide |

El estado del ciclo (si está abierto o cerrado, cuántos turnos lleva) se guarda en `andromarta/data/ciclo.json` para sobrevivir a reinicios. Si querés **forzar la apertura inmediata de un ciclo nuevo** sin esperar al sorteo, borrá ese archivo: la próxima vez que llegue un mensaje, Andromarta lo crea abierto en 0 turnos y vuelve a responder.

### 3. Cuándo arranca Andromarta una conversación sola (iniciativa)

Andromarta corre por dentro un "reloj" que cada cierto rato hace un sorteo: si gana, ella le manda un mensaje a Aikiu por iniciativa propia (y eso abre un ciclo nuevo). Hay tres cosas que controlan ese reloj:

#### a) Cada cuánto se hace el sorteo

Está en `andromarta/scheduler.py`, línea con `INTERVALO_CHECK_SEG = 60 * 15` (= 15 minutos). Para sortear más seguido cambialo a `60 * 5` (cada 5 min), por ejemplo. Para sortear cada media hora, `60 * 30`.

#### b) A partir de cuánto silencio Andromarta se "aburre"

Mismo archivo, línea `SILENCIO_DISPARADOR_SEG = 60 * 60 * 2` (= 2 horas). Si Clara llevaba más de ese tiempo sin escribir, la probabilidad de que Andromarta dispare iniciativa se multiplica por 2,5 (cap en 90%). Bajarlo (ej. `60 * 30` = media hora) la hace más insistente; subirlo, más tranquila.

#### c) Probabilidad base según la hora del día

Está en `andromarta/estado.py`, función `probabilidad_iniciativa`. Los valores actuales son:

| Franja | Hora | Probabilidad en cada sorteo |
|---|---|---|
| Mañana | 06:00–11:00 | 35% |
| Mediodía | 11:00–14:00 | 15% |
| Tarde | 14:00–18:00 | 25% |
| Noche | 18:00–22:00 | 20% |
| Madrugada | 22:00–06:00 | 2% (casi nunca; insomnio esporádico) |

Cada vez que dispara iniciativa en el mismo día, la probabilidad se reduce a la mitad (para no ser cargosa). Si querés que sea más conversadora, subí esos números; si la querés más reservada, bajalos.

#### Ejemplo concreto

Con los defaults: a media tarde (probabilidad 25%) y sin haber disparado todavía hoy, **en promedio Andromarta arranca conversación sola cada ~60 minutos** (porque cada 15 min hay un 25% de chance: 1/0.25 = 4 sorteos = 60 min). Si llevás 2 horas sin escribirle, ese promedio cae a ~25 minutos.

### 4. Cuánto pasa entre que Clara manda voz y Andromarta la transcribe

Esto no es configurable: depende de lo que tarde Groq Whisper en procesar el audio (típicamente 1–3 segundos para audios de hasta 30 s).

### Tabla resumen — todos los tiempos en un vistazo

| Qué controla | Variable / archivo | Default | Dónde se cambia |
|---|---|---|---|
| ¿Simula pausas humanas? | `ANDROMARTA_RITMO_HUMANO` | `0` (no) | `andromarta/.env` |
| Tope de mensajes por conversación | `ANDROMARTA_MAX_TURNOS_CICLO` | `15` | `andromarta/.env` |
| Cada cuánto sortea iniciativa | `INTERVALO_CHECK_SEG` | 15 min | `andromarta/scheduler.py` |
| Cuánto silencio activa el "se aburre" | `SILENCIO_DISPARADOR_SEG` | 2 h | `andromarta/scheduler.py` |
| Probabilidad de iniciativa por franja | función `probabilidad_iniciativa` | 35/15/25/20/2% | `andromarta/estado.py` |
| Pausa de "lectura" (solo con ritmo humano) | función `_pausa_lectura` | 1,5–9,5 s | `andromarta/bot.py` |
| Pausa de "tipeo" (solo con ritmo humano) | función `_pausa_tipeo` | 2–20 s | `andromarta/bot.py` |
| Pausa de "grabación" (solo con ritmo humano) | función `_pausa_grabacion` | 2–5 s | `andromarta/bot.py` |

---

## Para apagarla

En la terminal donde está corriendo, apretá `Ctrl + C`. Andromarta se cierra limpio y conserva todo: la sesión, el historial, el estado de ánimo del día.

Para volver a arrancarla: el comando del paso 5 alcanza.

---

## Si algo no funciona

**"No puedo encontrar al bot Aikiu"** o **"ANDROMARTA_AIKIU_USERNAME no resuelve"**
Telegram exige que la cuenta sintética y el bot se hayan saludado al menos una vez. Volvé al paso 3.

**Telegram me pide el código SMS pero no me llega**
Probá esperar 1 minuto y pedir reenvío. Si no llega, el número que pusiste en `ANDROMARTA_PHONE` está mal escrito o no es el de la cuenta. Verificá el `+` y el código de país.

**"GROQ_API_KEY no está seteada"**
La copiaste mal de un `.env` al otro. Asegurate de que en `andromarta/.env` la línea `GROQ_API_KEY=...` tiene el mismo valor que en el `.env` raíz del proyecto.

**Andromarta arrancó pero no escribe nunca**
Puede ser normal: durante el día arranca conversación cada tanto, no constantemente. Para forzarla, mandale un mensaje desde Aikiu (o pediles que se saluden ustedes mismos desde la cuenta sintética). Igualmente, mirá la terminal: si dice "Escuchando mensajes" y no tira errores, está bien.

**Quiero borrar todo y arrancar de cero**
Borrá la carpeta `andromarta/data/`. La próxima vez que la arranques, te va a pedir el código SMS otra vez y empieza el historial limpio.
