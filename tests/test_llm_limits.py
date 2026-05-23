"""Tests para core/llm_limits.py — catálogo de límites del free tier de Groq."""

from core import llm_limits


# ---------------------------------------------------------------------------
# es_audio
# ---------------------------------------------------------------------------

def test_es_audio_whisper_true():
    assert llm_limits.es_audio("whisper-large-v3") is True
    assert llm_limits.es_audio("whisper-large-v3-turbo") is True

def test_es_audio_case_insensitive():
    assert llm_limits.es_audio("WHISPER-large-v3") is True
    assert llm_limits.es_audio("Whisper-Large-V3") is True

def test_es_audio_chat_models_false():
    assert llm_limits.es_audio("llama-3.3-70b-versatile") is False
    assert llm_limits.es_audio("openai/gpt-oss-120b") is False
    assert llm_limits.es_audio("qwen/qwen3-32b") is False


# ---------------------------------------------------------------------------
# limites
# ---------------------------------------------------------------------------

def test_limites_devuelve_dict_para_modelo_catalogado():
    lim = llm_limits.limites("llama-3.3-70b-versatile")
    assert lim is not None
    assert lim["rpm"] == 30
    assert lim["rpd"] == 1_000
    assert lim["tpm"] == 12_000
    assert lim["tpd"] == 100_000

def test_limites_devuelve_none_para_modelo_desconocido():
    assert llm_limits.limites("modelo-inventado") is None
    assert llm_limits.limites("") is None

def test_limites_audio_tiene_ash_y_asd():
    lim = llm_limits.limites("whisper-large-v3")
    assert lim is not None
    assert lim["ash"] == 7_200
    assert lim["asd"] == 28_800


# ---------------------------------------------------------------------------
# tpd / tpm / rpm / rpd helpers
# ---------------------------------------------------------------------------

def test_tpd_modelo_conocido():
    assert llm_limits.tpd("llama-3.3-70b-versatile") == 100_000
    assert llm_limits.tpd("llama-3.1-8b-instant") == 500_000

def test_tpd_modelo_desconocido_es_none():
    assert llm_limits.tpd("inexistente") is None

def test_tpd_modelo_sin_tope_explicito():
    assert llm_limits.tpd("groq/compound") is None
    assert llm_limits.tpd("groq/compound-mini") is None

def test_tpm_modelo_conocido():
    assert llm_limits.tpm("llama-3.3-70b-versatile") == 12_000
    assert llm_limits.tpm("groq/compound") == 70_000

def test_tpm_modelo_desconocido():
    assert llm_limits.tpm("nope") is None

def test_rpm_modelo_conocido():
    assert llm_limits.rpm("llama-3.3-70b-versatile") == 30
    assert llm_limits.rpm("qwen/qwen3-32b") == 60

def test_rpm_modelo_desconocido():
    assert llm_limits.rpm("inventado") is None

def test_rpd_modelo_conocido():
    assert llm_limits.rpd("llama-3.3-70b-versatile") == 1_000
    assert llm_limits.rpd("llama-3.1-8b-instant") == 14_400

def test_rpd_modelo_desconocido():
    assert llm_limits.rpd("xxx") is None


# ---------------------------------------------------------------------------
# Sanidad del catálogo: shape y consistencia
# ---------------------------------------------------------------------------

def test_catalogo_tiene_modelo_default():
    """El modelo de chat default usado por el proyecto tiene que estar siempre catalogado."""
    assert "llama-3.3-70b-versatile" in llm_limits.FREE_TIER

def test_catalogo_tiene_modelo_whisper_default():
    assert "whisper-large-v3" in llm_limits.FREE_TIER

def test_todos_los_chat_models_tienen_rpm_tpm():
    for modelo, lim in llm_limits.FREE_TIER.items():
        if llm_limits.es_audio(modelo):
            continue
        # Chat: rpm y tpm tienen que estar definidos (no None)
        assert lim.get("rpm") is not None, f"{modelo} no tiene rpm"
        assert lim.get("tpm") is not None, f"{modelo} no tiene tpm"

def test_todos_los_audio_models_tienen_ash_asd():
    for modelo, lim in llm_limits.FREE_TIER.items():
        if not llm_limits.es_audio(modelo):
            continue
        assert lim.get("ash") is not None, f"{modelo} no tiene ash"
        assert lim.get("asd") is not None, f"{modelo} no tiene asd"
