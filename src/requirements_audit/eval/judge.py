"""LLM-as-judge for contradiction calls, calibrated against labeled items.

Hamel's doctrine (and the plan) require reporting judge **precision/recall vs
labels**, not raw agreement. `calibrate` runs the judge over `evals/judge_labels.json`
and reports all three. The labels are construction-derived from the seeded ground
truth (true conflicts → yes, near-misses and clearly-unrelated pairs → no); this is
disclosed in the README as the synthetic-corpus tradeoff, not blind human labeling.

Live only: needs an LLM. Tests inject a `TestModel`/`FunctionModel`.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model

_LABELS_PATH = Path(__file__).resolve().parents[3] / "evals" / "judge_labels.json"

INSTRUCTIONS = """\
You judge whether two engineering requirements genuinely contradict each other —
i.e. they cannot both hold for the same system under the same conditions.

Answer is_conflict=true only for a real contradiction. Answer false when the two
are consistent, including: values qualified to different modes/conditions, a value
that falls inside a range the other states, a reference to a current (non-superseded)
requirement, or two requirements that simply address unrelated topics. Give a
one-sentence rationale quoting the deciding phrase from each.
"""


class JudgeVerdict(BaseModel):
    is_conflict: bool
    rationale: str


judge_agent = Agent(output_type=JudgeVerdict, instructions=INSTRUCTIONS, name="judge")


class JudgeItem(BaseModel):
    req_a: str
    req_b: str
    text_a: str
    text_b: str
    label: bool  # gold: is this a true contradiction?
    note: str = ""


class JudgeCalibration(BaseModel):
    precision: float
    recall: float
    agreement: float
    n: int


def load_judge_labels(path: Path | None = None) -> list[JudgeItem]:
    raw = json.loads((path or _LABELS_PATH).read_text(encoding="utf-8"))
    return [JudgeItem(**item) for item in raw]


def _prompt(item: JudgeItem) -> str:
    return f"Requirement {item.req_a}:\n{item.text_a}\n\nRequirement {item.req_b}:\n{item.text_b}"


def calibrate(items: list[JudgeItem], *, model: Model | None = None) -> JudgeCalibration:
    """Run the judge over labeled items; report precision/recall/agreement vs labels."""
    tp = fp = fn = agree = 0
    for item in items:
        predicted = judge_agent.run_sync(_prompt(item), model=model).output.is_conflict
        if predicted == item.label:
            agree += 1
        if predicted and item.label:
            tp += 1
        elif predicted and not item.label:
            fp += 1
        elif not predicted and item.label:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return JudgeCalibration(
        precision=precision, recall=recall, agreement=agree / len(items), n=len(items)
    )
