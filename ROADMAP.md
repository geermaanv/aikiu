# Mejoras pendientes — Aikiu

## En progreso / Listo
- [x] Mover API keys a .env
- [x] Sistema de perfil en perfil.md (lenguaje natural)
- [x] Filtro de temas sensibles via perfil
- [x] Script guiado de configuración (bash configurar.sh)
- [x] Bot familiar en Telegram (familiar_bot.py) — ver y editar perfil por secciones

## Pendiente

### Alta prioridad
- [ ] Notificación al familiar: si el adulto mayor parece angustiado o pregunta
      temas preocupantes, el bot familiar recibe una alerta automática

### Media prioridad
- [ ] Detección de estado emocional: si Rosa suena triste, el bot
      lo registra y puede avisar al familiar
- [ ] Reporte al familiar: si Rosa pregunta temas preocupantes o
      parece angustiada, enviar alerta a un segundo chat_id (familiar)

### Baja prioridad / Ideas
- [ ] Historial persistente entre reinicios (ahora se pierde al cerrar)
- [ ] Panel web simple para que el familiar edite el perfil sin tocar archivos
