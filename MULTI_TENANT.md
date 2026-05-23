# Aikiu multi-tenant

Aikiu soporta múltiples adultos mayores (un adulto = un "hogar") en el
mismo proceso. Cada `/start` desde un Telegram nuevo crea un hogar
automáticamente con sus propios datos aislados.

Esta nota explica cómo funciona, qué cambió respecto al modo
single-tenant original y cómo desplegarlo en Railway con datos
persistentes.

## Modelo

```
+---------------------------+
|    aikiu.py (1 proceso)   |  ← un solo BOT_TOKEN
+---------------------------+
            |
            v
+---------------------------+
| instances/<chat_id>/...   |  ← un directorio por adulto
+---------------------------+
  ├── 1658290192/   (Marta)
  │   ├── state.json
  │   ├── perfil.md
  │   ├── stats.json
  │   ├── familiares.json
  │   ├── receptividad.json
  │   ├── usage.json
  │   ├── logs/YYYY-MM-DD.md
  │   └── heartbeat-*.json
  ├── 2049338101/   (Pepe)
  │   └── ...
  └── _invites.json         ← códigos compartidos (global, no por hogar)
      _familiar_state.json   ← estado de cada familiar (nombre, adulto activo)
```

### Por qué un proceso para todos

- Un solo `BOT_TOKEN` de Telegram = un solo proceso de polling.
- Los costos en Railway crecen lineal con cantidad de procesos, no con
  cantidad de hogares. Multi-tenant escala mucho más barato.
- Los hogares no se comunican entre sí (cada uno tiene su `chat_id` y su
  carpeta), así que el aislamiento es solo del lado del filesystem.

### Compatibilidad con single-tenant

Si hacés `git pull` sobre una instalación vieja, la migración se
ejecuta automáticamente la primera vez que arranca `aikiu.py`:

1. Detecta `state.json` en la raíz del repo (instalación single-tenant).
2. Crea `instances/<owner_chat_id>/` y mueve allí `state.json`,
   `perfil.md`, `stats.json`, `usage.json`, `familiares.json`,
   `receptividad.json`, `logs/` y los heartbeats.
3. Marca el `state.json` con `migrated_from_legacy: true` para que
   `admin /hogares` lo muestre.

La migración es idempotente: si la corrés dos veces no rompe nada (la
segunda vez no encuentra nada que mover).

## Onboarding de un nuevo adulto

1. El adulto abre el chat del bot principal y manda `/start`.
2. `aikiu.py` detecta que el `chat_id` no tiene hogar y crea uno nuevo
   en `instances/<chat_id>/` con un `state.json` mínimo.
3. Desde ese momento, todos los mensajes del adulto se procesan dentro
   del contexto de ese hogar: perfil propio, stats propios, log propio.

No hay límite de cantidad de hogares en el código (sí en los rate
limits del LLM, ver más abajo).

## Familiares vinculados a varios adultos (many-to-many)

Un familiar puede recibir alertas y enviar mensajes a varios adultos:

1. El adulto manda `/invitar` al bot principal → recibe un código
   alfanumérico de 6 caracteres (ej. `A3K9P2`). Vale 24 horas, un uso.
2. El familiar manda `/vincular A3K9P2` al bot familiar y queda
   asociado al hogar de ese adulto.
3. Si el familiar se vincula a un solo adulto, todos los comandos
   (`/perfil`, `/stats`, `/mensaje`, etc.) operan sobre ese adulto
   automáticamente.
4. Si se vincula a varios, fija el adulto activo con
   `/elegir <chat_id>`. Lista sus vínculos con `/misadultos`.

Los familiares ven alertas (distress, inactividad) solo del adulto al
que están vinculados — no se filtran datos entre hogares.

## LLM compartido (fair-use)

El `GROQ_API_KEY` se comparte entre todos los hogares del mismo deploy.
Los límites del free tier de Groq (RPM/TPM/RPD/TPD) aplican a la suma
de todas las conversaciones, no por hogar.

Si vas a desplegar con varios adultos activos:

- Considerá pasarte al tier pago de Groq y subir
  `GROQ_DAILY_TOKEN_LIMIT` para que los avisos de cuota del admin
  reflejen tu cuota real.
- El admin bot avisa con `/llm` cuando alguno de los modelos en uso
  está cerca del tope diario.
- Hoy no hay throttling por hogar (los 429 del free tier se recuperan
  solos cuando baja la ráfaga). Si en producción se vuelve un problema,
  se puede agregar.

## Deploy en Railway

### Pre-requisitos

1. Cuenta de Railway con un proyecto creado.
2. Bot tokens (BOT_TOKEN, FAMILIAR_BOT_TOKEN, ADMIN_BOT_TOKEN) creados
   en @BotFather.
3. `GROQ_API_KEY` de https://console.groq.com.

### Configuración

1. **Variables de entorno** (Railway → Variables):

   ```
   BOT_TOKEN=...
   GROQ_API_KEY=...
   FAMILIAR_BOT_TOKEN=...           # opcional
   ADMIN_BOT_TOKEN=...              # opcional
   AIKIU_REGISTRY=/data/instances   # MUY recomendado en producción
   ```

2. **Volumen persistente** (Railway → Volumes):

   - Crear un volumen montado en `/data`.
   - Setear `AIKIU_REGISTRY=/data/instances` para que los hogares
     vivan ahí y sobrevivan a cada redeploy.
   - Sin volumen, todo se pierde en el siguiente push (Railway por
     defecto tiene filesystem efímero).

3. **Procesos**: el `Procfile` define tres procesos:

   ```
   worker:   python aikiu.py
   familiar: python familiar_bot.py
   admin:    python admin/bot.py
   ```

   Por default Railway corre `worker`. Los otros dos se pueden
   habilitar desde la UI ("Add Service" → mismo repo, distinto
   `Start Command`) o usando un solo Service con `start.sh` (que
   lanza los tres en paralelo dentro del mismo contenedor).

### Verificación post-deploy

1. Mandá `/start` al bot principal desde un Telegram nuevo.
   - En la primera ejecución debería migrar el state legacy
     (si lo hay) y crear `/data/instances/<chat_id>/`.
2. Hablale al bot un par de mensajes para que aparezcan en `stats.json`.
3. Abrí el admin bot, mandá `/start` para registrarte como admin,
   y después `/hogares` para ver el hogar creado.
4. Mandá `/health` y verificá que los tres bots aparezcan en verde.

## Operación

### Admin

El bot admin tiene comandos específicos de multi-tenant:

- `/hogares` — lista todos los hogares con familiares, actividad y
  fecha de alta.
- `/borrar <chat_id>` — muestra info y pide confirmación.
- `/borrar <chat_id> CONFIRMAR` — borra recursivamente el directorio
  del hogar. Irreversible.

### Adulto

- `/start` — alta automática (la primera vez).
- `/invitar` — generar código para que un familiar se vincule.

### Familiar

- `/start` — alta automática.
- `/vincular <CODIGO>` — quedar asociado al hogar del adulto.
- `/misadultos` — listar los adultos vinculados (marca el activo).
- `/elegir <chat_id>` — fijar el adulto activo cuando hay varios.
- Resto de comandos (`/perfil`, `/stats`, `/mensaje`, `/aprendizajes`,
  `/editar`, `/suscriptores`) operan sobre el adulto activo.

## Diagnóstico de problemas

| Síntoma | Posible causa | Cómo verificar |
|---|---|---|
| Los datos se pierden en cada deploy | `AIKIU_REGISTRY` no apunta a un volumen persistente | `admin /hogares` muestra cero después del redeploy |
| Un familiar no recibe alertas | No se vinculó al adulto, o eligió otro adulto como activo | Que mande `/misadultos` en el bot familiar |
| 429 (rate limit) frecuentes | Free tier de Groq, varios adultos hablando a la vez | `admin /llm` muestra el ratio de errores; considerar tier pago |
| `admin /hogares` lista cero pero `/instancias` lista uno | El hogar está en la raíz del repo, todavía no migró | Reiniciá `aikiu.py` — la migración corre al arranque |

## Limitaciones conocidas

- **Andromarta** (humanoide sintético para testing) sigue siendo
  single-tenant — corre como un único usuario contra un único Aikiu.
  No se diseñó para multi-tenant.
- **Concurrencia** dentro de un hogar: las escrituras a `state.json` /
  `stats.json` / `perfil.md` son atómicas (escribir-y-renombrar) pero
  no hay lock entre hogares. Como cada hogar tiene su propia carpeta,
  no hay contención cruzada.
- **No hay límite de hogares** en el código. El cuello en producción
  va a ser la cuota del LLM antes que cualquier otra cosa.
