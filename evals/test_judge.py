"""LLM-judge calibration eval.

Gate (deterministic): the labels file is well-formed and balanced, and the judge
wiring computes correct precision/recall against a stubbed model.

Live (skipped without keys): the real judge clears the calibration floors.
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from requirements_audit.eval.judge import calibrate, load_judge_labels
from requirements_audit.eval.thresholds import Thresholds

pytestmark = pytest.mark.eval


def test_judge_labels_are_balanced_and_well_formed() -> None:
    items = load_judge_labels()
    assert len(items) >= 30
    n_true = sum(i.label for i in items)
    n_false = len(items) - n_true
    assert n_true >= 10 and n_false >= 10, (n_true, n_false)
    for item in items:
        assert item.text_a.strip() and item.text_b.strip()


def test_calibration_math_with_oracle_model() -> None:
    """A perfect oracle (echoes the gold label) yields precision == recall == 1.0."""
    labels = load_judge_labels()
    gold = {frozenset((i.req_a, i.req_b)): i.label for i in labels}

    def oracle(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        import re

        text = "".join(
            getattr(p, "content", "") or ""
            for m in messages
            for p in m.parts
            if getattr(p, "part_kind", "") == "user-prompt"
        )
        ids = re.findall(r"Requirement (\S+?):", text)
        verdict = gold.get(frozenset(ids[:2]), False)
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=info.output_tools[0].name,
                    args={"is_conflict": verdict, "rationale": "oracle"},
                )
            ]
        )

    result = calibrate(labels, model=FunctionModel(oracle))
    assert result.n == len(labels)
    assert result.precision == 1.0 and result.recall == 1.0 and result.agreement == 1.0


def test_judge_calibration_meets_live_thresholds(
    thresholds: Thresholds, live_model: object
) -> None:
    result = calibrate(load_judge_labels(), model=live_model)  # type: ignore[arg-type]
    judge = thresholds.live.judge
    assert result.precision >= judge.precision_min, result.model_dump()
    assert result.recall >= judge.recall_min, result.model_dump()
