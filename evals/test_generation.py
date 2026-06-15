"""Generation eval via Ragas (live; skipped without keys + the eval extra).

The sample-assembly half is checked deterministically with a FunctionModel so the
dataset shape is gated; the Ragas scoring half runs only in the nightly/live job.
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from requirements_audit.config import Settings
from requirements_audit.eval.ragas_eval import build_samples, evaluate_generation
from requirements_audit.eval.thresholds import Thresholds
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion

pytestmark = pytest.mark.eval


def _stub_qa(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    props = set(info.output_tools[0].parameters_json_schema.get("properties", {}))
    if "route" in props:  # planner
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={"route": "qa", "subqueries": [], "rationale": "x"},
                )
            ]
        )
    tool_returned = any(isinstance(p, ToolReturnPart) for m in messages for p in m.parts)
    if not tool_returned:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="hybrid_search", args={"query": "x", "k": 3})]
        )
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name=info.output_tools[0].name,
                args={"question": "q", "text": "a grounded answer", "citations": []},
            )
        ]
    )


def test_build_samples_shape(store: SqliteStore, golden_questions: list[GoldenQuestion]) -> None:
    """Deterministic: assemble Ragas samples for the success questions (no Ragas call)."""
    samples = build_samples(store, golden_questions, Settings(), model=FunctionModel(_stub_qa), k=5)
    assert samples, "expected samples for success-scenario questions"
    for s in samples:
        assert s.question and s.answer and s.ground_truth
        assert s.contexts and all(c.strip() for c in s.contexts)


def test_generation_meets_live_thresholds(
    store: SqliteStore,
    golden_questions: list[GoldenQuestion],
    thresholds: Thresholds,
    live_model: object,
) -> None:
    pytest.importorskip("ragas", reason="ragas is an eval-only extra")
    samples = build_samples(store, golden_questions, Settings(), model=live_model)  # type: ignore[arg-type]
    gen = evaluate_generation(samples)
    live = thresholds.live.generation
    assert gen.faithfulness >= live.faithfulness_min, gen.model_dump()
    assert gen.answer_relevancy >= live.answer_relevancy_min, gen.model_dump()
    assert gen.context_precision >= live.context_precision_min, gen.model_dump()
