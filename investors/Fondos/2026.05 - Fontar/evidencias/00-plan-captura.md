# Plan de evidencias FONTAR — Aikiu TRL 3-4

**Base documental:** `formulario.md` §19, `ROADMAP.md`, `tests/checklist.md`, `investors/guion-demo.md`  
**Carpeta destino:** `evidencias/` (esta carpeta)  
**Fecha sugerida en cada archivo:** la del día de captura

---

## 1. Mapa: 15 flujos → archivos

| # | Flujo (ROADMAP) | Archivo propuesto | Formato |
|---|-----------------|-------------------|---------|
| 1 | Saludo matutino + temperatura | `13-saludo-matutino-temperatura.png` | Captura + audio opcional |
| 2 | Voz → STT → Clara audio | `04-telegram-marta.png` o clip en `03-demo.mp4` | Video + captura |
| 3 | Texto → texto | `14-conversacion-texto.png` | Captura |
| 4 | Recordatorio medicación 09:00 | `15-recordatorio-medicacion-0900.png` | Captura + audio |
| 5 | Pre-routing clima (wttr.in) | `16-tool-clima-wttr.png` | Captura |
| 6 | Pre-routing dólar | `17-tool-dolar-dolarapi.png` | Captura |
| 7 | Pre-routing noticias | `18-tool-noticias-rss.png` | Captura |
| 8 | DISTRESS 1 + alerta amarilla | `19-distress-nivel1-familiar.png` | Captura |
| 9 | DISTRESS 2 + alerta naranja | `20-distress-nivel2-familiar.png` | Captura |
| 10 | DISTRESS 3 + alerta roja (simulación) | `21-distress-nivel3-SIMULACION.png` | Captura etiquetada |
| 11 | Alerta inactividad N horas | `07-alerta-inactividad.png` | Captura |
| 12 | Puente familiar voz + nombre | `22-puente-familiar-voz.png` | Video o 2 capturas |
| 13 | Comandos `/perfil`, `/editar`, `/mensaje`, `/suscriptores` | `06-bot-familiar-comandos.png` | Collage 4 paneles |
| 14 | `perfil.md` diff análisis nocturno | `08-analisis-nocturno-diff.md` | Diff markdown |
| 15 | Degradación si falla API externa | `23-degradacion-api-fallo.png` | Captura + nota |

**Paquete núcleo §19 (formulario):** `01`–`12` se mantienen como en `formulario.md` §19.1.

---

## 2. Inventario completo (01–27)

```
evidencias/
├── 00-plan-captura.md          ← este archivo
├── 00-indice-evidencias.md     ← completar al cerrar capturas + hashes
├── 01-tests-output.png
├── 02-log-anonimizado.txt
├── 03-demo.mp4
├── 04-telegram-marta.png
├── 05-telegram-familiar.png
├── 06-bot-familiar-comandos.png
├── 07-alerta-inactividad.png
├── 08-analisis-nocturno-diff.md
├── 09-arquitectura.png
├── 10-distress-level.pdf
├── 11-validacion-piloto.pdf
├── 12-carta-usuaria.pdf
├── 13-saludo-matutino-temperatura.png
├── 14-conversacion-texto.png
├── 15-recordatorio-medicacion-0900.png
├── 16-tool-clima-wttr.png
├── 17-tool-dolar-dolarapi.png
├── 18-tool-noticias-rss.png
├── 19-distress-nivel1-familiar.png
├── 20-distress-nivel2-familiar.png
├── 21-distress-nivel3-SIMULACION.png
├── 22-puente-familiar-voz.png
├── 23-degradacion-api-fallo.png
├── 24-terminal-arranque.png      (opcional)
├── 25-config-recordatorios.yml.png (opcional)
└── 26-informe-tecnico-trl4.pdf   (opcional)
```

---

## 3. Pre-vuelo

```bash
cd /Users/germanv/proyectos/aikiu-1
source venv/bin/activate
bash start.sh
# Verificar: "Aikiu escuchando" y "Alertas al familiar activadas"
```

- **Teléfono A:** chat de Marta con Clara  
- **Teléfono B:** bot familiar  
- **Mac:** terminal + editor para `perfil.md`

---

## 4. Pasos por flujo (resumen)

| Flujo | Acción | Archivo |
|-------|--------|---------|
| 1 Saludo | `python probar_saludo.py` | `13` |
| 2 Voz | Nota de voz a Clara → respuesta audio | `04` / `03` |
| 3 Texto | "Hola" → respuesta texto | `14` |
| 4 Medicación | Esperar 09:00 o ajustar hora en `config.yml` + reiniciar | `15` |
| 5 Clima | "¿Qué tiempo hace hoy?" | `16` |
| 6 Dólar | "¿A cuánto está el dólar?" | `17` |
| 7 Noticias | "¿Qué noticias hay hoy?" | `18` |
| 8 Distress 1 | "Me siento muy sola" → alerta 🟡 en bot familiar | `19` |
| 9 Distress 2 | "Estoy llorando, me siento muy mal" → 🟠 | `20` |
| 10 Distress 3 | Simulación etiquetada; avisar familiares antes | `21` |
| 11 Inactividad | 4+ h sin mensaje o umbral bajo temporal | `07` |
| 12 Puente | `/nombre` + `/mensaje` con nota de voz | `22` |
| 13 Comandos | Collage `/perfil`, `/editar`, `/mensaje`, `/suscriptores` | `06` |
| 14 Nocturno | `cp perfil.md perfil.md.antes` → correr análisis → `diff -u` | `08` |
| 15 Degradación | WiFi off antes de consulta clima | `23` |

**Mensajes de prueba:** ver `tests/checklist.md` §§2–5.

**DISTRESS nivel 3:** watermark **"SIMULACIÓN TÉCNICA — PRUEBA FONTAR"**; avisar familiares antes; no reutilizar crisis reales en capturas.

---

## 5. Video único `03-demo.mp4` (≈3:30)

1. Voz Marta↔Clara  
2. Clima + dólar (10 s c/u)  
3. "Me siento muy sola" → teléfono B 🟡  
4. `/mensaje` familiar → Marta recibe audio  
5. Narración: saludo 08:30, medicación, inactividad  
6. Cierre: 111 tests + piloto  

Los niveles distress 1–3 van mejor en capturas `19`–`21`, no en un video largo.

---

## 6. Anonimización (antes de exportar)

| Dato | Acción |
|------|--------|
| Familiares | Iniciales o "Familiar 1" |
| `chat_id` | `***6789` |
| Teléfonos, emails, direcciones | Tapar |
| Medicación/diagnósticos | Generalizar |
| API keys | Nunca en captura |

En `00-indice-evidencias.md`: fecha, notas, `shasum -a 256` por archivo.

---

## 7. Prioridad si falta tiempo

**Must-have:** `01`, `03`, `05` o `19`, `21` (simulación), `06`, `16`, `09`, `10`, `02`  

**Nice-to-have:** `17`, `18`, `14`, `13`, `15`, `20`, `07`, `08`, `23`, `11`, `12`

**Orden en una sesión (~90 min):** pytest → saludo → texto/voz/tools → distress 1–2 → simulación 3 → bot familiar → degradación → armar `03` → anonimizar → índice.

---

## 8. Alineación TRL 4 (formulario)

| Claim | Evidencia |
|-------|-----------|
| STT+LLM+TTS | `03`, `04`, `14` |
| DISTRESS 0–3 | `10`, `19`–`21`, `05` |
| Pre-routing | `16`–`18`, `23` |
| Supervisión familiar | `06`, `22`, `05` |
| Proactividad | `13`, `15`, `07` + `03` |
| Aprendizaje nocturno | `08` |
| 111 tests | `01` |
| Piloto real | `11`, `12`, `04` |

---

Ver también: `../formulario.md` §19, `../../../guion-demo.md`, `../../../../tests/checklist.md`.
