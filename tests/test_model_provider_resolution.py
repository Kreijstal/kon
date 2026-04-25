import pytest

from kon.llm.models import ApiType, fetch_all_available_models, get_model


def test_get_model_prefers_provider_when_specified():
    copilot = get_model("gpt-5.5", "github-copilot")
    openai = get_model("gpt-5.5", "openai-codex")

    assert copilot is not None
    assert openai is not None
    assert copilot.provider == "github-copilot"
    assert openai.provider == "openai-codex"
    assert copilot.api != openai.api


def test_get_model_falls_back_to_id_lookup():
    model = get_model("claude-sonnet-4.6-copilot")

    assert model is not None
    assert model.provider == "github-copilot"


def test_get_model_prefers_provider_for_gpt_5_5():
    copilot = get_model("gpt-5.5", "github-copilot")
    openai = get_model("gpt-5.5", "openai-codex")

    assert copilot is not None
    assert openai is not None
    assert copilot.provider == "github-copilot"
    assert openai.provider == "openai-codex"
    assert copilot.api != openai.api


def test_get_model_resolves_deepseek_models():
    model = get_model("deepseek-v4-flash", "deepseek")

    assert model is not None
    assert model.provider == "deepseek"


def test_get_model_resolves_grok_4_5():
    model = get_model("grok-4.5", "xai")

    assert model is not None
    assert model.provider == "xai"
    assert model.api == ApiType.XAI_RESPONSES
    assert model.base_url == "https://api.x.ai/v1"
    assert model.max_tokens == 500000
    assert model.context_window == 500000
    assert model.supports_images is True
    assert model.supports_thinking is True


def test_get_model_resolves_gpt_5_6_codex_models():
    for model_id in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        model = get_model(model_id, "openai-codex")

        assert model is not None
        assert model.provider == "openai-codex"
        assert model.api == ApiType.OPENAI_CODEX_RESPONSES
        assert model.context_window == 372000
        assert model.supports_images is True
        assert model.supports_thinking is True
        assert model.uses_responses_lite is True


def test_get_model_resolves_gpt_5_6_copilot_models():
    for model_id in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"):
        model = get_model(model_id, "github-copilot")

        assert model is not None
        assert model.provider == "github-copilot"
        assert model.api == ApiType.GITHUB_COPILOT_RESPONSES
        assert model.context_window == 372000
        assert model.supports_images is True
        assert model.supports_thinking is True
        assert model.uses_responses_lite is False


@pytest.mark.asyncio
async def test_fetch_all_available_models_keeps_deepseek_fallback(monkeypatch):
    async def fail_fetch(*args, **kwargs):
        raise RuntimeError("model listing unavailable")

    monkeypatch.setattr("kon.llm.models.fetch_models_from_api", fail_fetch)

    models = await fetch_all_available_models()

    assert any(m.id == "deepseek-v4-flash" and m.provider == "deepseek" for m in models)
