"""Provider abstraction: build the PydanticAI model from `Settings`.

Anthropic is primary, OpenAI the fallback (README: "provider fallback Anthropic ↔
OpenAI"). Only providers whose API key is present are wired, so this is called
exclusively on live runs — tests inject `TestModel`/`FunctionModel` via
`agent.override(...)` and never reach here. Constructing a model performs no
network I/O; the first request does.
"""

from __future__ import annotations

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider

from requirements_audit.config import Provider, Settings


class MissingCredentialsError(RuntimeError):
    """Raised when a live run is requested but no provider API key is configured."""


def _single_model(settings: Settings, provider: Provider) -> Model | None:
    if provider is Provider.ANTHROPIC:
        if not settings.anthropic_api_key:
            return None
        return AnthropicModel(
            settings.llm_model,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key),
        )
    if not settings.openai_api_key:
        return None
    return OpenAIChatModel(
        settings.openai_model,
        provider=OpenAIProvider(api_key=settings.openai_api_key),
    )


def build_model(settings: Settings) -> Model:
    """A single model, or a `FallbackModel` if both providers are configured."""
    primary = _single_model(settings, settings.llm_provider)
    fallback = (
        _single_model(settings, settings.llm_fallback_provider)
        if settings.llm_fallback_provider
        else None
    )
    models = [m for m in (primary, fallback) if m is not None]
    if not models:
        raise MissingCredentialsError(
            "No LLM API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
            "or run the deterministic path (audit numeric/superseded classes) which needs no key."
        )
    return models[0] if len(models) == 1 else FallbackModel(*models)
