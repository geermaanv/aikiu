"""
Tests del flujo de alerta con indagación previa.

Ante un síntoma (nivel 1-2) NO se alerta de inmediato: queda pendiente, Aikiu
repregunta, y con la respuesta se confirma o se descarta. El nivel 3
(emergencia) nunca espera. Si el adulto deja de responder, el timeout alerta
igual — el silencio tras un síntoma es más grave, no menos.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import aikiu
from core.distress import reset_cooldowns


def _run(coro):
    return asyncio.run(coro)


def _family_bot():
    fb = MagicMock()
    fb.send_message = AsyncMock()
    return fb


def _setup(monkeypatch, tmp_path, chat_id=777):
    """Aísla el pendiente y el historial en tmp; sin tareas cosméticas."""
    monkeypatch.setattr(aikiu, "_pendiente_path", lambda cid: tmp_path / "pend.json")
    monkeypatch.setattr(aikiu, "_get_historial", lambda cid: [])
    monkeypatch.setattr(aikiu, "registrar_log", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "registrar_stats", lambda *a, **k: None)
    monkeypatch.setattr(aikiu, "clasificar_receptividad", AsyncMock())
    monkeypatch.setattr("core.alerts.cargar_suscriptores", lambda cid=None: [1])
    reset_cooldowns()
    aikiu._limpiar_pendiente(chat_id)
    return chat_id


def test_sintoma_no_alerta_de_inmediato_queda_pendiente(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    monkeypatch.setattr(aikiu, "clasificar_distress", AsyncMock(return_value=(1, "dolor de rodilla")))
    _run(aikiu._evaluar_distress_y_extras("me duele un poco la rodilla", "¿Te duele mucho?", cid, fb))
    fb.send_message.assert_not_awaited()          # todavía no se avisa
    assert aikiu._leer_pendiente(cid)["nivel"] == 1


def test_confirmacion_dispara_la_alerta(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    monkeypatch.setattr(aikiu, "clasificar_distress", AsyncMock(return_value=(1, "dolor de rodilla")))
    _run(aikiu._evaluar_distress_y_extras("me duele la rodilla", "¿Te duele mucho?", cid, fb))
    monkeypatch.setattr(aikiu, "evaluar_confirmacion", AsyncMock(return_value=("confirma", 2)))
    _run(aikiu._evaluar_distress_y_extras("me sigue doliendo mucho", "Entiendo.", cid, fb))
    fb.send_message.assert_awaited()               # ahora sí
    assert not aikiu._leer_pendiente(cid)          # pendiente resuelto


def test_descarte_no_alerta(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    monkeypatch.setattr(aikiu, "clasificar_distress", AsyncMock(return_value=(1, "dolor de rodilla")))
    _run(aikiu._evaluar_distress_y_extras("me duele la rodilla", "¿Te duele?", cid, fb))
    monkeypatch.setattr(aikiu, "evaluar_confirmacion", AsyncMock(return_value=("descarta", 0)))
    _run(aikiu._evaluar_distress_y_extras("no, ya se me pasó", "Me alegro.", cid, fb))
    fb.send_message.assert_not_awaited()           # era menor → no se molesta a la familia
    assert not aikiu._leer_pendiente(cid)


def test_emergencia_alerta_sin_indagar(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    monkeypatch.setattr(aikiu, "clasificar_distress", AsyncMock(return_value=(3, "caída, no puede levantarse")))
    _run(aikiu._evaluar_distress_y_extras("me caí y no me puedo levantar", "Ya aviso.", cid, fb))
    fb.send_message.assert_awaited()               # inmediata, sin esperar respuesta
    assert not aikiu._leer_pendiente(cid)


def test_timeout_alerta_si_dejo_de_responder(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    app = MagicMock()
    app.bot_data = {"family_bot": fb}
    # Pendiente creada hace más del timeout, sin respuesta del adulto
    viejo = (datetime.now() - timedelta(minutes=aikiu._PENDIENTE_TIMEOUT_MIN + 1)).isoformat()
    aikiu.write_json_atomic(aikiu._pendiente_path(cid), {
        "nivel": 2, "motivo": "mencionó una caída", "texto": "me caí", "ts": viejo,
    })
    _run(aikiu.verificar_pendientes(app, chat_id=cid))
    fb.send_message.assert_awaited()
    texto = fb.send_message.await_args.kwargs["text"]
    assert "no respondió" in texto                 # la familia se entera del silencio
    assert not aikiu._leer_pendiente(cid)


def test_timeout_no_alerta_si_es_reciente(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    app = MagicMock()
    app.bot_data = {"family_bot": fb}
    aikiu.write_json_atomic(aikiu._pendiente_path(cid), {
        "nivel": 1, "motivo": "dolor", "texto": "me duele", "ts": datetime.now().isoformat(),
    })
    _run(aikiu.verificar_pendientes(app, chat_id=cid))
    fb.send_message.assert_not_awaited()           # todavía puede contestar
    assert aikiu._leer_pendiente(cid)


def test_alerta_incluye_contexto_de_la_charla(monkeypatch, tmp_path):
    cid = _setup(monkeypatch, tmp_path)
    fb = _family_bot()
    monkeypatch.setattr(aikiu, "_get_historial", lambda c: [
        {"role": "user", "content": "hoy me levanté cansada"},
        {"role": "assistant", "content": "Qué lástima, descansá."},
        {"role": "user", "content": "me caí en la cocina"},
    ])
    monkeypatch.setattr(aikiu, "clasificar_distress", AsyncMock(return_value=(3, "mencionó una caída")))
    _run(aikiu._evaluar_distress_y_extras("me caí en la cocina", "¿Estás bien?", cid, fb))
    texto = fb.send_message.await_args.kwargs["text"]
    assert "Cómo venía la charla" in texto
    assert "me levanté cansada" in texto            # contexto, no solo la línea que disparó


def test_chat_create_trata_respuesta_vacia_como_falla(monkeypatch):
    """OpenRouter devuelve 200 con content vacío: sin este chequeo el vigía
    lo leía como 'nivel 0' y perdía la alerta en silencio."""
    monkeypatch.setitem(aikiu.CONFIG, "proveedor_llm", "openrouter")
    vacia = MagicMock()
    vacia.choices = [MagicMock()]
    vacia.choices[0].message.content = ""
    fake_or = MagicMock()
    fake_or.chat.completions.create = AsyncMock(return_value=vacia)
    buena = MagicMock()
    buena.choices = [MagicMock()]
    buena.choices[0].message.content = "NIVEL: 2\nMOTIVO: dolor persistente"
    fake_groq = MagicMock()
    fake_groq.chat.completions.create = AsyncMock(return_value=buena)
    with patch("aikiu.openrouter", fake_or), patch("aikiu.groq", fake_groq):
        r = _run(aikiu._chat_create(model="z-ai/glm-5", messages=[], max_tokens=40))
    assert "NIVEL: 2" in r.choices[0].message.content   # cayó a Groq en vez de devolver vacío
