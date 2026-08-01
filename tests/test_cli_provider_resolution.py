from kon import config as kon_config
from kon.llm import resolve_provider_api_type
from kon.llm.models import ApiType
from kon.runtime import ConversationRuntime, default_base_url_for_api


def test_resolve_provider_api_type_known_provider():
    assert resolve_provider_api_type("github-copilot") == ApiType.GITHUB_COPILOT
    assert resolve_provider_api_type("openai") == ApiType.OPENAI_COMPLETIONS
    assert resolve_provider_api_type("xai") == ApiType.XAI_RESPONSES


def test_resolve_provider_api_type_unknown_provider():
    try:
        resolve_provider_api_type("invalid-provider")
    except ValueError as exc:
        assert "Unknown provider 'invalid-provider'" in str(exc)
        assert "Valid providers:" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid provider")


def testdefault_base_url_for_api_openai_completions(monkeypatch):
    monkeypatch.setenv("KON_BASE_URL", "http://localhost:1234/v1")
    assert default_base_url_for_api(ApiType.OPENAI_COMPLETIONS) == "http://localhost:1234/v1"


def testdefault_base_url_for_api_non_openai_completions():
    assert default_base_url_for_api(ApiType.ANTHROPIC_COPILOT) is None


def _runtime(
    monkeypatch,
    *,
    base_url: str | None = None,
    default_provider: str = "deepseek",
    default_base_url: str = "https://proxy.example.com/v1",
) -> ConversationRuntime:
    monkeypatch.setattr(kon_config.llm, "default_provider", default_provider)
    monkeypatch.setattr(kon_config.llm, "default_base_url", default_base_url)
    return ConversationRuntime(
        cwd="/test/project",
        model="deepseek-v4-flash",
        model_provider=default_provider,
        api_key=None,
        base_url=base_url,
        thinking_level="none",
        tools=[],
    )


def test_non_default_provider_model_uses_its_own_base_url(monkeypatch):
    rt = _runtime(monkeypatch)

    _, url = rt._model_api_and_base_url("gpt-5.6-luna", "openai-codex")

    assert url == "https://chatgpt.com/backend-api"


def test_model_without_explicit_provider_resolves_own_provider_base_url(monkeypatch):
    rt = _runtime(monkeypatch)

    _, url = rt._model_api_and_base_url("gpt-5.6-sol", None)

    assert url == "https://chatgpt.com/backend-api"


def test_default_provider_keeps_config_base_url_override(monkeypatch):
    rt = _runtime(monkeypatch)

    _, url = rt._model_api_and_base_url("deepseek-v4-flash", "deepseek")

    assert url == "https://proxy.example.com/v1"


def test_explicit_base_url_wins_over_model_default(monkeypatch):
    rt = _runtime(monkeypatch, base_url="http://localhost:11434/v1")

    _, url = rt._model_api_and_base_url("gpt-5.6-luna", "openai-codex")

    assert url == "http://localhost:11434/v1"
