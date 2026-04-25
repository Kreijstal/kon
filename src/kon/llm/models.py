"""
Manually maintained model catalog.

Add models here as needed. Each model defines its capabilities,
API type, and any special handling (e.g., vision fallback model).
"""
# TODO: should use something like https://github.com/anomalyco/models.dev in future

from dataclasses import dataclass
from enum import Enum

DEFAULT_MAX_TOKENS = 16384


class ApiType(Enum):
    OPENAI_COMPLETIONS = "openai-completions"
    OPENAI_RESPONSES = "openai-responses"
    OPENAI_CODEX_RESPONSES = "openai-codex-responses"
    XAI_RESPONSES = "xai-responses"
    ANTHROPIC_COPILOT = "anthropic-copilot"
    AZURE_AI_FOUNDRY = "azure-ai-foundry"
    GITHUB_COPILOT = "github-copilot"
    GITHUB_COPILOT_RESPONSES = "github-copilot-responses"


@dataclass
class Model:
    id: str  # Model ID (e.g., "glm-5.1", "claude-opus-4.6")
    provider: str  # "openai", "zhipu", "github-copilot", "openai-codex"
    api: ApiType  # Which API format to use
    base_url: str  # API endpoint
    max_tokens: int  # Max output tokens
    supports_images: bool  # Native vision support
    supports_thinking: bool  # Reasoning/thinking support
    context_window: int | None = None  # Max context (None = use config default)
    vision_model: str | None = None  # Fallback vision model if no native support
    uses_responses_lite: bool = False  # Codex Responses Lite request contract


MODELS: dict[str, Model] = {
    # ZhiPu models
    "glm-5.1": Model(
        id="glm-5.1",
        provider="zhipu",
        api=ApiType.OPENAI_COMPLETIONS,
        base_url="https://api.z.ai/api/coding/paas/v4",
        max_tokens=8192,
        supports_images=True,
        supports_thinking=True,
    ),
    "glm-5.2": Model(
        id="glm-5.2",
        provider="zhipu",
        api=ApiType.OPENAI_COMPLETIONS,
        base_url="https://api.z.ai/api/coding/paas/v4",
        max_tokens=65536,
        supports_images=True,
        supports_thinking=True,
        context_window=131072,
    ),
    # DeepSeek models (OpenAI-compatible Chat Completions API)
    "deepseek-v4-flash": Model(
        id="deepseek-v4-flash",
        provider="deepseek",
        api=ApiType.OPENAI_COMPLETIONS,
        base_url="https://api.deepseek.com",
        max_tokens=8192,
        supports_images=False,
        supports_thinking=True,
    ),
    "deepseek-v4-pro": Model(
        id="deepseek-v4-pro",
        provider="deepseek",
        api=ApiType.OPENAI_COMPLETIONS,
        base_url="https://api.deepseek.com",
        max_tokens=8192,
        supports_images=False,
        supports_thinking=True,
    ),
    # xAI models (Grok/X subscription OAuth via Responses API)
    "grok-4.5": Model(
        id="grok-4.5",
        provider="xai",
        api=ApiType.XAI_RESPONSES,
        base_url="https://api.x.ai/v1",
        max_tokens=500000,
        supports_images=True,
        supports_thinking=True,
        context_window=500000,
    ),
    # GitHub Copilot models - Claude (uses Anthropic Messages API for thinking support)
    "claude-sonnet-4.6-copilot": Model(
        id="claude-sonnet-4.6",
        provider="github-copilot",
        api=ApiType.ANTHROPIC_COPILOT,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    "claude-opus-4.6-copilot": Model(
        id="claude-opus-4.6",
        provider="github-copilot",
        api=ApiType.ANTHROPIC_COPILOT,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    # GitHub Copilot models - GPT/Codex (uses OpenAI Responses API)
    "gpt-5.6-sol-copilot": Model(
        id="gpt-5.6-sol",
        provider="github-copilot",
        api=ApiType.GITHUB_COPILOT_RESPONSES,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
    ),
    "gpt-5.6-terra-copilot": Model(
        id="gpt-5.6-terra",
        provider="github-copilot",
        api=ApiType.GITHUB_COPILOT_RESPONSES,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
    ),
    "gpt-5.6-luna-copilot": Model(
        id="gpt-5.6-luna",
        provider="github-copilot",
        api=ApiType.GITHUB_COPILOT_RESPONSES,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
    ),
    "gpt-5.5-copilot": Model(
        id="gpt-5.5",
        provider="github-copilot",
        api=ApiType.GITHUB_COPILOT_RESPONSES,
        base_url="https://api.individual.githubcopilot.com",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    # OpenAI Codex OAuth models (ChatGPT Plus/Pro subscription)
    "gpt-5.6-sol": Model(
        id="gpt-5.6-sol",
        provider="openai-codex",
        api=ApiType.OPENAI_CODEX_RESPONSES,
        base_url="https://chatgpt.com/backend-api",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
        uses_responses_lite=True,
    ),
    "gpt-5.6-terra": Model(
        id="gpt-5.6-terra",
        provider="openai-codex",
        api=ApiType.OPENAI_CODEX_RESPONSES,
        base_url="https://chatgpt.com/backend-api",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
        uses_responses_lite=True,
    ),
    "gpt-5.6-luna": Model(
        id="gpt-5.6-luna",
        provider="openai-codex",
        api=ApiType.OPENAI_CODEX_RESPONSES,
        base_url="https://chatgpt.com/backend-api",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
        context_window=372000,
        uses_responses_lite=True,
    ),
    "gpt-5.5": Model(
        id="gpt-5.5",
        provider="openai-codex",
        api=ApiType.OPENAI_CODEX_RESPONSES,
        base_url="https://chatgpt.com/backend-api",
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    # Azure AI Foundry models (Anthropic via Azure)
    "claude-sonnet-4.6-azure": Model(
        id="claude-sonnet-4.6",
        provider="azure-ai-foundry",
        api=ApiType.AZURE_AI_FOUNDRY,
        base_url="",  # resolved from AZURE_AI_FOUNDRY_BASE_URL env var
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    "claude-opus-4.6-azure": Model(
        id="claude-opus-4.6",
        provider="azure-ai-foundry",
        api=ApiType.AZURE_AI_FOUNDRY,
        base_url="",  # resolved from AZURE_AI_FOUNDRY_BASE_URL env var
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
    # Azure AI Foundry - Opus 4.7
    "claude-opus-4.7-azure": Model(
        id="claude-opus-4.7",
        provider="azure-ai-foundry",
        api=ApiType.AZURE_AI_FOUNDRY,
        base_url="",  # resolved from AZURE_AI_FOUNDRY_BASE_URL env var
        max_tokens=8192 * 2,
        supports_images=True,
        supports_thinking=True,
    ),
}


def get_model(model_id: str, provider: str | None = None) -> Model | None:
    if provider:
        for model in MODELS.values():
            if model.id == model_id and model.provider == provider:
                return model

    direct = MODELS.get(model_id)
    if direct:
        return direct

    for model in MODELS.values():
        if model.id == model_id:
            return model

    return None


def get_all_models() -> list[Model]:
    return list(MODELS.values())


def get_models_by_provider(provider: str) -> list[Model]:
    return [m for m in MODELS.values() if m.provider == provider]


def get_max_tokens(model_id: str) -> int:
    model = MODELS.get(model_id)
    return model.max_tokens if model else DEFAULT_MAX_TOKENS


# Providers that support dynamic model listing via /models endpoint
DYNAMIC_MODEL_PROVIDERS: frozenset[str] = frozenset(
    {"opencode", "kilocode", "zaicodingplan", "zhipu", "openai", "openrouter", "deepseek"}
)

# Default base URLs for dynamic providers
PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    "opencode": "https://opencode.ai/zen/v1",
    "kilocode": "https://api.kilo.ai/api/openrouter",
    "zaicodingplan": "https://api.z.ai/api/coding/paas/v4",
    "zhipu": "https://api.z.ai/api/coding/paas/v4",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com",
}


async def fetch_models_from_api(
    base_url: str, api_key: str | None = None, provider: str | None = None
) -> list[str]:
    """Fetch available models from an OpenAI-compatible /models endpoint.

    Args:
        base_url: The API base URL
        api_key: Optional API key (some providers don't need one)
        provider: Provider name for special handling (e.g., 'opencode', 'kilocode')

    Returns:
        List of model IDs available from the API
    """
    from openai import AsyncOpenAI

    # Handle provider-specific requirements
    is_opencode = provider == "opencode" or "opencode.ai" in base_url
    is_kilocode = provider == "kilocode" or "api.kilo.ai" in base_url
    is_openrouter = provider == "openrouter" or "openrouter.ai" in base_url

    if is_opencode:
        # OpenCode requires empty API key
        client = AsyncOpenAI(api_key="", base_url=base_url)
    elif is_kilocode:
        if not api_key:
            raise ValueError("Kilocode requires an API key")
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers={"x-api-key": api_key, "X-KILOCODE-EDITORNAME": "kon"},
        )
    elif is_openrouter:
        # OpenRouter /models endpoint is public, no key needed for listing
        client = AsyncOpenAI(api_key=api_key or "sk-placeholder", base_url=base_url)
    else:
        if not api_key:
            api_key = "placeholder"  # Some APIs don't require auth
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    try:
        models = await client.models.list()
        return [m.id for m in models.data]
    finally:
        await client.close()


async def fetch_all_available_models(
    provider_configs: dict[str, dict] | None = None,
) -> list[Model]:
    """Fetch all available models, combining hardcoded and dynamic models.

    Args:
        provider_configs: Optional dict of provider configs from config.toml
            e.g., {"opencode": {"base_url": "...", "api_key": "..."}}

    Returns:
        List of Model objects, with dynamic models for supported providers
    """
    import asyncio
    import os

    models: list[Model] = list(MODELS.values())
    known_models = {(model.provider, model.id) for model in models}

    # Fetch dynamic models for each dynamic provider
    async def fetch_for_provider(provider: str) -> list[Model]:
        provider_models: list[Model] = []

        base_url = PROVIDER_DEFAULT_BASE_URLS.get(provider, "")
        api_key: str | None = None

        # Get config from provider_configs if available
        if provider_configs and provider in provider_configs:
            cfg = provider_configs[provider]
            base_url = cfg.get("base_url") or base_url
            api_key = cfg.get("api_key")

        # Fall back to environment variables
        if not api_key:
            env_var = f"{provider.upper().replace('-', '_')}_API_KEY"
            api_key = os.environ.get(env_var)

        if not base_url:
            return provider_models

        try:
            model_ids = await fetch_models_from_api(base_url, api_key, provider)
            for model_id in model_ids:
                provider_models.append(
                    Model(
                        id=model_id,
                        provider=provider,
                        api=ApiType.OPENAI_COMPLETIONS,
                        base_url=base_url,
                        max_tokens=8192,
                        supports_images=False,
                        supports_thinking=True,
                    )
                )
        except Exception:
            # If fetch fails, return empty list for this provider
            pass

        return provider_models

    # Fetch all dynamic providers in parallel
    tasks = [fetch_for_provider(p) for p in DYNAMIC_MODEL_PROVIDERS]
    results = await asyncio.gather(*tasks)

    for provider_models in results:
        for model in provider_models:
            key = (model.provider, model.id)
            if key not in known_models:
                models.append(model)
                known_models.add(key)

    return models
