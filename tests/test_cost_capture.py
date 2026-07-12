"""Per-request token/cost capture tests — deterministic FunctionModels, no keys."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic_ai.models.function import FunctionModel

from requirements_audit.api.app import create_app
from requirements_audit.config import Settings
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.llm.pricing import MODEL_PRICING_USD_PER_MTOK, estimate_usd
from requirements_audit.orchestrator import answer_query, run_audit
from tests.test_agents import _qa_fn
from tests.test_api import _CORPUS, _qa_model, _settings


def test_estimate_usd_prices_pinned_models_and_refuses_unknown() -> None:
    price = estimate_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
    input_rate, output_rate = MODEL_PRICING_USD_PER_MTOK["claude-sonnet-4-6"]
    assert price == input_rate + output_rate
    # An unpriced model must be None (shown as "unpriced"), never a silent $0.
    assert estimate_usd("some-unpinned-model", 1000, 1000) is None


def test_query_trace_carries_usage_totals_and_estimate(store: SqliteStore) -> None:
    settings = Settings()
    _, trace = answer_query(
        store, "What is the watchdog timeout?", settings, model=FunctionModel(_qa_fn)
    )

    usage = trace.metadata["usage"]
    # Planner + analyst both ran (the analyst makes 2 requests: tool call + answer).
    assert usage["requests"] >= 2
    assert usage["input_tokens"] > 0 and usage["output_tokens"] > 0
    # Priced against the configured (pinned) primary model, and labeled with it.
    assert trace.metadata["pricing_model"] == settings.llm_model
    assert trace.metadata["estimated_usd"] == estimate_usd(
        settings.llm_model, usage["input_tokens"], usage["output_tokens"]
    )


def test_deterministic_audit_reports_zero_usage(store: SqliteStore) -> None:
    _, trace = run_audit(store, Settings(), model=None, use_llm=False)

    usage = trace.metadata["usage"]
    assert usage == {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    # Zero tokens price to $0.0 — fine, the CLI/API render it as "no LLM calls".
    assert trace.metadata["estimated_usd"] in (0.0, None)


def test_api_trace_summary_exposes_usage(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(tmp_path), model_factory=_qa_model))
    assert client.post("/ingest", json={"corpus_dir": str(_CORPUS)}).status_code == 200

    audit_trace = client.post("/audit", json={"use_llm": False}).json()["trace"]
    assert audit_trace["usage"]["requests"] == 0
    assert "estimated_usd" in audit_trace
