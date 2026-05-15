"""
Tests para el sistema de alertas de inactividad.
Cubre: lógica de umbral, cooldown diario, baseline, config activa/inactiva,
y el mensaje que recibe el familiar.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


def _make_app(family_bot=None):
    app = MagicMock()
    app.bot_data = {"family_bot": family_bot or AsyncMock()}
    return app


def _config(activa=True, horas=4, checks=None):
    return {
        "alerta_inactividad": {
            "activa": activa,
            "horas_umbral": horas,
            "checks": checks or ["11:30", "19:00"],
        }
    }


# ---------------------------------------------------------------------------
# Lógica de verificar_inactividad
# ---------------------------------------------------------------------------

def test_no_alerta_sin_baseline():
    """Sin _ultima_actividad, nunca debe alertar."""
    import aikiu
    aikiu._ultima_actividad = None
    aikiu._alerta_inactividad_fecha = None
    with patch("aikiu.CONFIG", _config()):
        run(aikiu.verificar_inactividad(_make_app()))
    # No debe haber cambiado la fecha (nunca llegó al envío)
    assert aikiu._alerta_inactividad_fecha is None

def test_no_alerta_dentro_del_umbral():
    """Si la última actividad fue hace menos de horas_umbral, no alertar."""
    import aikiu
    aikiu._ultima_actividad = datetime.now() - timedelta(hours=2)
    aikiu._alerta_inactividad_fecha = None
    with patch("aikiu.CONFIG", _config(horas=4)), \
         patch("aikiu.notify_inactividad", new=AsyncMock()) as mock_notify:
        run(aikiu.verificar_inactividad(_make_app()))
    mock_notify.assert_not_called()

def test_alerta_cuando_supera_umbral():
    """Si se supera horas_umbral sin actividad, debe alertar."""
    import aikiu
    async def caso():
        aikiu._ultima_actividad = datetime.now() - timedelta(hours=5)
        aikiu._alerta_inactividad_fecha = None
        notificado = []
        async def fake_notify(**kwargs):
            notificado.append(kwargs["horas"])
        pending = []
        with patch("aikiu.CONFIG", _config(horas=4)), \
             patch("aikiu.notify_inactividad", side_effect=fake_notify), \
             patch("aikiu.create_background_task", side_effect=lambda c: pending.append(c)):
            await aikiu.verificar_inactividad(_make_app())
        for c in pending:
            await c
        assert notificado, "Debería haber alertado"
        assert notificado[0] == 5
    run(caso())

def test_no_repite_en_mismo_dia():
    """Una vez alertado hoy, no vuelve a alertar en el mismo día."""
    import aikiu
    hoy = datetime.now().date()
    aikiu._ultima_actividad = datetime.now() - timedelta(hours=6)
    aikiu._alerta_inactividad_fecha = hoy
    with patch("aikiu.CONFIG", _config(horas=4)), \
         patch("aikiu.notify_inactividad", new=AsyncMock()) as mock_notify, \
         patch("aikiu.create_background_task", side_effect=lambda coro: run(coro)):
        run(aikiu.verificar_inactividad(_make_app()))
    mock_notify.assert_not_called()

def test_alerta_nuevo_dia_aunque_ya_se_alerto_ayer():
    """Al día siguiente, vuelve a alertar si Rosa sigue sin escribir."""
    import aikiu
    async def caso():
        ayer = (datetime.now() - timedelta(days=1)).date()
        aikiu._ultima_actividad = datetime.now() - timedelta(hours=8)
        aikiu._alerta_inactividad_fecha = ayer
        notificado = []
        async def fake_notify(**kwargs):
            notificado.append(True)
        pending = []
        with patch("aikiu.CONFIG", _config(horas=4)), \
             patch("aikiu.notify_inactividad", side_effect=fake_notify), \
             patch("aikiu.create_background_task", side_effect=lambda c: pending.append(c)):
            await aikiu.verificar_inactividad(_make_app())
        for c in pending:
            await c
        assert notificado, "Al día siguiente debe alertar de nuevo"
    run(caso())

def test_no_alerta_si_desactivada_en_config():
    """alerta_inactividad.activa: false desactiva el sistema."""
    import aikiu
    aikiu._ultima_actividad = datetime.now() - timedelta(hours=10)
    aikiu._alerta_inactividad_fecha = None
    with patch("aikiu.CONFIG", _config(activa=False)), \
         patch("aikiu.notify_inactividad", new=AsyncMock()) as mock_notify:
        run(aikiu.verificar_inactividad(_make_app()))
    mock_notify.assert_not_called()

def test_no_alerta_sin_family_bot():
    """Sin family_bot configurado, no debe romper."""
    import aikiu
    aikiu._ultima_actividad = datetime.now() - timedelta(hours=6)
    aikiu._alerta_inactividad_fecha = None
    app = MagicMock()
    app.bot_data = {"family_bot": None}
    with patch("aikiu.CONFIG", _config(horas=4)):
        run(aikiu.verificar_inactividad(app))  # no debe lanzar excepción

def test_registra_fecha_al_alertar():
    """Al enviar la alerta, debe guardar la fecha de hoy."""
    import aikiu
    async def caso():
        aikiu._ultima_actividad = datetime.now() - timedelta(hours=5)
        aikiu._alerta_inactividad_fecha = None
        pending = []
        with patch("aikiu.CONFIG", _config(horas=4)), \
             patch("aikiu.notify_inactividad", new=AsyncMock()), \
             patch("aikiu.create_background_task", side_effect=lambda c: pending.append(c)):
            await aikiu.verificar_inactividad(_make_app())
        assert aikiu._alerta_inactividad_fecha == datetime.now().date()
    run(caso())


# ---------------------------------------------------------------------------
# notify_inactividad — formato del mensaje
# ---------------------------------------------------------------------------

def test_mensaje_inactividad_incluye_horas():
    from core.alerts import notify_inactividad
    ultima = datetime(2026, 5, 15, 8, 30)
    mensajes = []
    async def fake_send(chat_id, text, parse_mode):
        mensajes.append(text)
    bot = MagicMock()
    bot.send_message = fake_send
    with patch("core.alerts.cargar_suscriptores", return_value=[123]):
        run(notify_inactividad(horas=5, ultima_actividad=ultima, family_bot=bot))
    assert mensajes
    assert "5 horas" in mensajes[0]

def test_mensaje_inactividad_incluye_timestamp():
    from core.alerts import notify_inactividad
    ultima = datetime(2026, 5, 15, 8, 30)
    mensajes = []
    async def fake_send(chat_id, text, parse_mode):
        mensajes.append(text)
    bot = MagicMock()
    bot.send_message = fake_send
    with patch("core.alerts.cargar_suscriptores", return_value=[123]):
        run(notify_inactividad(horas=5, ultima_actividad=ultima, family_bot=bot))
    assert "08:30" in mensajes[0]

def test_mensaje_inactividad_singular_una_hora():
    """'1 hora' en singular, no '1 horas'."""
    from core.alerts import notify_inactividad
    ultima = datetime(2026, 5, 15, 10, 0)
    mensajes = []
    async def fake_send(chat_id, text, parse_mode):
        mensajes.append(text)
    bot = MagicMock()
    bot.send_message = fake_send
    with patch("core.alerts.cargar_suscriptores", return_value=[123]):
        run(notify_inactividad(horas=1, ultima_actividad=ultima, family_bot=bot))
    assert "1 hora" in mensajes[0]
    assert "1 horas" not in mensajes[0]

def test_mensaje_inactividad_tono_no_alarmista():
    """El mensaje debe incluir la frase de tranquilización."""
    from core.alerts import notify_inactividad
    ultima = datetime(2026, 5, 15, 9, 0)
    mensajes = []
    async def fake_send(chat_id, text, parse_mode):
        mensajes.append(text)
    bot = MagicMock()
    bot.send_message = fake_send
    with patch("core.alerts.cargar_suscriptores", return_value=[123]):
        run(notify_inactividad(horas=4, ultima_actividad=ultima, family_bot=bot))
    assert "puede estar bien" in mensajes[0].lower()
