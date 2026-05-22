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
```

Detalles:

- **`GROQ_API_KEY`**: la misma que usa Aikiu (está en el `.env` raíz del proyecto). Copiala tal cual.
- **`ANDROMARTA_PHONE`**: el número del celular sintético, con el `+` y el código de país. Ejemplo: `+5491138271234`.
- **`ANDROMARTA_AIKIU_USERNAME`**: el username del bot de prueba que creaste, **sin la arroba**.
- **`ANDROMARTA_VOZ_PROB`**: probabilidad de que Andromarta responda con audio en vez de texto. `0` = solo texto. `1` = solo audio. `0.4` = más o menos 4 de cada 10.

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

A veces Andromarta arranca la conversación sola (cada 15 minutos hay un sorteo para ver si lo hace). A veces espera que Aikiu le hable primero. Si no pasa nada en mucho rato, mandale un mensaje vos desde el bot (o desde Aikiu) y va a contestar.

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
