"""Runtime configuration — one typed `Settings` object, sourced from env / `.env`.

Importing this module never touches the network and never requires API keys: a
bare `Settings()` is valid with no environment at all (keys default to None). Keys
are only consulted when an agent actually talks to a live provider, so the CLI,
the deterministic audit path, and the whole CI eval gate run without secrets.

Model versions are pinned here (not scattered through the agents) so a model bump
is a one-line, reviewable change — `requirements-audit.agent.md` → "pinned model
versions in config.py".
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── LLM providers (keys optional; only needed for live runs) ───────────────
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    llm_provider: Provider = Provider.OPENAI
    llm_fallback_provider: Provider | None = Provider.ANTHROPIC

    # Pinned model versions (one place to bump). `llm_model` is the Anthropic
    # model, `openai_model` the OpenAI one; `primary_model` resolves whichever
    # the configured primary provider uses.
    llm_model: str = "claude-sonnet-4-6"
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # ─── Run budgets / loop caps (PydanticAI UsageLimits + orchestrator) ────────
    max_agent_steps: int = 12
    max_tokens_per_run: int = 200_000
    max_usd_per_run: float = 0.50
    # Upper bound on candidate pairs handed to the LLM comparator in an audit.
    max_audit_pairs: int = 60

    # ─── Local stores ───────────────────────────────────────────────────────────
    sqlite_path: Path = Path("data/requirements.sqlite")

    # ─── LangFuse (tracing; absent keys => tracing is a no-op) ───────────────────
    langfuse_host: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def model_for(self, provider: Provider) -> str:
        return self.llm_model if provider is Provider.ANTHROPIC else self.openai_model

    @property
    def primary_model(self) -> str:
        """The model the configured primary provider runs — what cost estimates price."""
        return self.model_for(self.llm_provider)
