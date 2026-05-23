# Cómo usar el bot admin — guía paso a paso

El bot admin es un **tercer bot de Telegram** que te avisa cómo viene Aikiu: si los procesos están vivos, cuántos tokens del LLM se gastaron, cuántas alertas se mandaron, las últimas líneas del log, etc. Lo usan vos y el equipo que opere Aikiu — admite hasta 5 chat_ids por default (configurable). Nadie más lo ve.

Esta guía te lleva desde cero hasta tenerlo respondiéndote en el celular.

---

## Antes de empezar — lo que tenés que tener

1. **Aikiu instalado y andando** en alguna computadora (la tuya o un servidor). Si Aikiu todavía no arranca, primero hacé eso siguiendo el `README.md` del proyecto.
2. **Telegram en el celular** (o en Telegram Desktop) con tu cuenta personal.
3. **5 minutos** y acceso a la computadora donde corre Aikiu para editar un archivo y reiniciar el bot.

Importante: **no uses el bot principal (`@aikiu_bot`) ni el familiar para administrar**. El admin es un bot aparte, recién creado. Hay tres motivos:

- Separás permisos: el adulto mayor conversa con su bot, los familiares con el suyo, y vos administrás con el tuyo.
- Si alguien le mete el dedo al bot del adulto mayor, no puede ver el dashboard de admin.
- Los comandos de admin (`/health`, `/llm`, etc.) no confunden al adulto mayor con cosas técnicas.

---

## Paso 1 — Crear el bot admin con @BotFather

Esto se hace una sola vez, desde la cuenta personal **tuya** (no la del adulto mayor).

1. Abrí Telegram con **tu cuenta personal**.
2. Buscá `@BotFather` (es el bot oficial de Telegram para crear bots) y abrí el chat.
3. Mandale `/newbot`.
4. Te va a pedir un **nombre para el bot**. Poné algo claro para vos, por ejemplo `Aikiu Admin Rosa` o `Aikiu Monitor`. Este nombre lo ves vos en tu lista de chats.
5. Te va a pedir un **username único**, que tiene que terminar en `bot`. Probá algo como `aikiu_admin_TUNOMBRE_bot`. Si está tomado, probá variantes.
6. Si lo acepta, te devuelve un mensaje con un **token**. Es una cadena larga que arranca con números y dos puntos:

   ```
   1234567890:AAH-abcdefGHIJKlmnop_qrstuvWxyz
   ```

7. **Copiá ese token y guardalo en un papel o en un documento privado.** Lo vas a pegar en el archivo `.env` en el paso siguiente.

> El token es **una contraseña**. Cualquiera que lo tenga puede actuar como tu bot admin. No lo mandes por chat, no lo subas a internet, no lo pongas en una captura de pantalla.

---

## Paso 2 — Pegar el token en `.env`

Aikiu lee los tokens de un archivo llamado `.env` que vive en la **raíz del proyecto** (no dentro de `admin/`).

1. Abrí la carpeta del proyecto Aikiu en el explorador de archivos de la computadora donde corre.
2. Buscá el archivo `.env` (el que ya usás para el bot principal). Si no lo ves, prendé "Mostrar archivos ocultos" en el explorador.
3. Abrilo con el Bloc de notas o cualquier editor de texto.
4. Buscá una línea que diga:

   ```
   ADMIN_BOT_TOKEN=PEGA_TU_ADMIN_BOT_TOKEN_AQUI
   ```

   Si no existe, agregala en una línea nueva al final del archivo.

5. Reemplazá `PEGA_TU_ADMIN_BOT_TOKEN_AQUI` por el token que te dio @BotFather en el paso 1. Quedaría:

   ```
   ADMIN_BOT_TOKEN=1234567890:AAH-abcdefGHIJKlmnop_qrstuvWxyz
   ```

6. Guardá el archivo y cerralo.

---

## Paso 3 — Reiniciar Aikiu para que levante el bot admin

El admin no arranca solo: se prende cuando reiniciás Aikiu con `start.sh` y `start.sh` se da cuenta de que ahora hay un `ADMIN_BOT_TOKEN` configurado.

1. Andá a la terminal donde está corriendo Aikiu.
2. Apretá `Ctrl + C` para detenerlo.
3. Volvé a arrancar:
   - **Mac / Linux**: `bash start.sh`
   - **Windows**: `.\startWin.ps1`
4. En las primeras líneas tenés que ver algo como:

   ```
   Aikiu iniciando...
   Bot familiar activo.
   Bot admin activo.
   ```

   Si dice "Bot admin activo", está vivo. Si no aparece, revisá el paso 2 (el token está mal pegado o quedó con `PEGA_TU` adelante).

> **Alternativa** si solo querés arrancar el admin a mano (sin levantar todo Aikiu): desde la raíz del proyecto, ejecutá `python admin/bot.py`. Pero lo normal es que el admin viva al lado del resto y arranque con `start.sh`.

---

## Paso 4 — Registrarte como admin desde el celular

El bot admin tiene una regla de seguridad: **cada `/start` desde un chat distinto suma un admin nuevo hasta llenar el cupo** (5 por default). Cuando el cupo está lleno, el resto de los `/start` se rechazan en silencio. Esto sirve para que un equipo se sume todo junto en los primeros minutos de la puesta en marcha; después de eso, la puerta queda cerrada.

1. En tu celular, abrí Telegram con tu cuenta personal.
2. Tocá la lupa de búsqueda arriba.
3. Escribí el username del bot admin que creaste (sin la arroba, por ejemplo `aikiu_admin_TUNOMBRE_bot`).
4. Tocá el resultado para abrir el chat.
5. Tocá **"Iniciar"** (botón abajo) o escribí `/start` y mandalo.
6. El bot te responde algo como:

   ```
   ✅ Hola TU_NOMBRE, primer admin registrado.
   Detecté 1 instancia(s) bajo monitoreo.

   ...menú con todos los comandos...
   ```

Si ves ese mensaje, listo: ya sos admin.

### Sumar al resto del equipo (hasta 5 personas)

Apenas vos quedás registrado, los otros integrantes del equipo pueden hacer exactamente lo mismo: cada uno abre el bot en su Telegram, manda `/start`, y queda registrado como admin #2, #3, etc. hasta llenar el cupo. Todos son pares: cualquiera puede usar todos los comandos.

> **Importante:** durante el bootstrap el cupo está abierto. Si publicás el username del bot o lo pegás en un grupo grande, alguien que no sea de tu equipo podría sumarse antes que tu gente y ocupar un lugar. Para evitarlo:
>
> - Avisale al equipo **antes** de arrancar el bot, así todos mandan `/start` al toque.
> - Si querés total control, usá la opción de la sección [Fijar los admins desde `.env`](#fijar-los-admins-desde-env) más abajo: ahí cableás los chat_ids y nadie más entra.

### Comandos de equipo

Una vez que estás registrado, tenés estos comandos para ver y mantener la lista:

- `/admins` — muestra los chat_ids registrados, cuántos lugares quedan, quién está fijado por `.env` y quién no.
- `/quitar_admin <chat_id>` — saca a un admin de la lista. Tomá el chat_id de la salida de `/admins`. Cualquiera de los 5 puede quitar a cualquiera (incluido a sí mismo).

### Cambiar el cupo (más o menos de 5)

Por default el cupo es 5. Si tu equipo es más chico (o más grande) podés ajustarlo agregando esta línea en el `.env` raíz del proyecto:

```
ADMIN_MAX_USERS=3
```

Reiniciá Aikiu y el bot va a aplicar el cupo nuevo. Si ya había más admins registrados que el cupo nuevo, los anteriores siguen siendo válidos, pero no se permiten registros adicionales hasta que la lista baje.

### Fijar los admins desde `.env`

Si preferís evitar el TOFU abierto (porque vas a publicar el bot en un servidor compartido, porque ya sabés los chat_ids del equipo, o porque querés que la lista no cambie nunca), podés fijarlos por variable de entorno:

1. Cada integrante del equipo se manda `/start` a `@userinfobot` desde su cuenta personal para obtener su chat_id (un número entero).
2. En el `.env` raíz del proyecto, agregá:

   ```
   ADMIN_CHAT_IDS=111111,222222,333333,444444,555555
   ```

3. Reiniciá Aikiu.

Con `ADMIN_CHAT_IDS` seteada, **solo esos chats** pueden usar el bot admin, sin importar quién mande `/start` primero. Los comandos `/quitar_admin` y los `/start` nuevos quedan deshabilitados — la lista la maneja el `.env`. Es la opción más segura.

> Por retrocompatibilidad sigue funcionando la vieja `ADMIN_CHAT_ID=123` (singular). Si la tenés seteada y querés ampliarla, pasala a `ADMIN_CHAT_IDS=123,456,...`.

---

## Paso 5 — Probar los comandos

En el menú azul al lado de la caja de texto (botón con líneas horizontales) deberías ver la lista de comandos. Si no aparece, esperá unos segundos y reabrí el chat.

Probá uno por uno:

| Comando | Para qué sirve |
|---|---|
| `/health` | Te dice si los bots (principal, familiar, admin) están vivos. Verde = todo OK, amarillo = tardando, rojo = algo se rompió. |
| `/llm` | Cuántos tokens del LLM gastaste hoy, en los últimos 7 días y en los últimos 30. Detecta automáticamente qué modelos están en uso (si conviven varios, los muestra todos por separado con sus respectivos límites) y te avisa si te estás acercando al tope del free tier de Groq de cada uno. |
| `/metricas` | Cuántos mensajes intercambió Aikiu con el adulto mayor, alertas mandadas, aprendizajes del análisis nocturno. |
| `/instancias` | Lista de instancias detectadas. Si tenés una sola instalación, va a aparecer una sola línea. |
| `/logs` | Últimas 30 líneas del log de Aikiu. Útil cuando algo se rompe y querés ver qué pasó. `/logs 50` para 50 líneas. `/logs err` para ver solo errores. |
| `/admins` | Lista los chat_ids con permiso de admin, cuántos lugares quedan, y de dónde viene cada uno (TOFU o `.env`). |
| `/quitar_admin <chat_id>` | Saca a un admin de la lista. Tomá el chat_id de la salida de `/admins`. Solo funciona si la lista no está fijada por `.env`. |
| `/ayuda` | Vuelve a mostrarte el menú con la descripción de cada uno. |

Si todo funciona, ya tenés un panel de monitoreo en el bolsillo.

---

## Para apagar el bot admin

No lo apagás solo: el admin arranca y se detiene junto con el resto de Aikiu. Si parás Aikiu con `Ctrl + C` en la terminal donde corre, también se va el admin.

Si querés **desactivar** el bot admin sin desinstalar nada (por ejemplo porque te molestan las notificaciones), borrá o comentá la línea `ADMIN_BOT_TOKEN=...` en `.env` y reiniciá Aikiu. La próxima vez no va a levantar el admin.

---

## Si algo no funciona

**"Mandé /start y el bot no contesta nada"**
Hay tres causas posibles:

- El bot no está corriendo. Revisá la terminal donde arrancaste Aikiu: ¿dice "Bot admin activo"? Si no, volvé al paso 3.
- El **cupo está lleno** y vos no estás en la lista. Pedile a alguien del equipo que tenga acceso que corra `/admins` para confirmar, y `/quitar_admin <chat_id>` para hacerte lugar (o usá la sección [Resetear todos los admins](#resetear-todos-los-admins) abajo si nadie tiene acceso).
- Los admins están fijados por `.env` (`ADMIN_CHAT_IDS`) y tu chat_id no figura ahí. Pedile al que mantiene el `.env` que te sume y reinicie Aikiu.

**"Me responde pero dice que no me reconoce"**
Igual que el caso anterior: no estás en la lista de admins. Verificá con `/admins` (desde la cuenta de alguien que sí esté) o resetealo.

**"El bot anda pero los comandos no aparecen en el menú azul"**
A veces Telegram tarda en sincronizar la lista de comandos. Cerrá y abrí el chat, o escribilos a mano (`/health`, `/llm`, etc.). Funcionan igual.

**"`/health` me muestra todo rojo o ausente"**
Significa que los bots están caídos. Mirá la terminal donde arrancaste Aikiu para ver el error, o usá `/logs err` para ver las últimas líneas problemáticas.

**"`/llm` me muestra muchos errores 429 (rate limit) pero el contador diario está bajo"**
Es lo más confuso del free tier de Groq. El bot mide tokens consumidos por día (TPD), pero los 429 casi nunca vienen del diario: vienen del **TPM** (tokens por minuto). Cuando `/llm` detecta que la mayoría de los errores son 429, te tira los TPM y RPM exactos del/los modelo(s) que estás usando — leelos ahí mismo en el chat.

Para referencia, los topes del free tier para los modelos más usados:

| Modelo | RPM | RPD | TPM | TPD |
|---|---|---|---|---|
| `llama-3.3-70b-versatile` | 30 | 1.000 | **12k** | 100k |
| `llama-3.1-8b-instant` | 30 | 14.400 | 6k | 500k |
| `meta-llama/llama-4-scout-17b-16e-instruct` | 30 | 1.000 | 30k | 500k |
| `qwen/qwen3-32b` | 60 | 1.000 | 6k | 500k |

Una nota de voz larga + transcripción + respuesta + audio TTS puede comer entre 3.000 y 5.000 tokens. Con 3 o 4 mensajes seguidos del adulto se llega al tope por minuto y empiezan los 429. Se destraba solo en cuanto pasa el minuto. Si te pasa seguido, las opciones son:

- Esperar a que la ráfaga baje (es lo más común — el problema desaparece solo).
- Pasar al tier de pago de Groq (Developer): mismo modelo pero límites 10× más altos.
- Cambiar a un modelo más chico. `llama-3.1-8b-instant` tiene **14.400 requests/día** y rara vez se choca contra el cuello, a costa de respuestas un poco peores.

> La tabla canónica vive en `core/llm_limits.py`. Si Groq cambia las cuotas o si querés agregar un modelo nuevo, ese archivo es el único que hay que tocar para que el admin lo refleje. El resto del repo lee de ahí.

**"`/llm` me dice 'casi en el tope diario'"**
Estás cerca del TPD del modelo. Por default el admin usa el TPD del free tier de Groq para cada modelo (`core/llm_limits.py`). Si tenés tier pago, podés forzar un valor manual con la variable `GROQ_DAILY_TOKEN_LIMIT` en `.env`: ese override aplica a todos los modelos. Para el free tier es raro llegar al diario en uso personal — si lo estás reventando, probablemente el adulto está mandando muchísimos mensajes y conviene revisar primero el TPM.

**"`/llm` me dice '(modelo no catalogado)'"**
Estás usando un modelo de Groq que todavía no está en `core/llm_limits.py`. El resto del reporte sigue funcionando, pero los avisos de cuota se omiten porque no sabemos contra qué límite comparar. Agregalo al diccionario `FREE_TIER` con los valores de https://console.groq.com/docs/rate-limits y la próxima vez el admin lo va a tratar como a los demás.

---

## Resetear todos los admins

Si la lista quedó desbalanceada (te lo robaron, se registró alguien por error, querés rearmar el equipo desde cero), podés borrar todos los admins persistidos:

1. Detené Aikiu con `Ctrl + C`.
2. Desde la carpeta del proyecto, ejecutá:

   ```
   python -c "from admin.state import reset_admin; reset_admin()"
   ```

3. Volvé a arrancar Aikiu (`bash start.sh` o `.\startWin.ps1`).
4. Cada integrante del equipo manda `/start` al bot admin en orden hasta llenar el cupo nuevamente.

Alternativa más rápida: borrá el archivo `admin/admin_state.json` a mano. Hace exactamente lo mismo.

> El reset no afecta a la lista de `ADMIN_CHAT_IDS` del `.env`: esa siempre manda. Si querés borrar admins fijados por `.env`, editá el `.env` y reiniciá.
