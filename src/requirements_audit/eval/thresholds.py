"""Typed loader for ``evals/thresholds.yaml``.

Thresholds live in data, not code, so tuning the eval gate is a reviewable config
change rather than an edit to test logic. The file has two sections: ``gate``
(deterministic, enforced on every commit with no API keys) and ``live`` (Ragas /
judge / full-pipeline metrics, enforced only in the nightly/live job).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "evals" / "thresholds.yaml"


class RetrievalThresholds(BaseModel):
    k: int
    precision_at_k: float
    recall_at_k: float


class GateThresholds(BaseModel):
    retrieval: RetrievalThresholds
    deterministic_recall_min: int  # numeric + superseded true conflicts found, no LLM


class GenerationThresholds(BaseModel):
    faithfulness_min: float
    answer_relevancy_min: float
    context_precision_min: float


class ContradictionLiveThresholds(BaseModel):
    full_recall_min: int  # of 15 true conflicts, with the LLM comparator
    critic_precision_min: float  # precision after the Critic filter


class JudgeThresholds(BaseModel):
    precision_min: float
    recall_min: float


class LiveThresholds(BaseModel):
    generation: GenerationThresholds
    contradiction: ContradictionLiveThresholds
    judge: JudgeThresholds


class Thresholds(BaseModel):
    gate: GateThresholds
    live: LiveThresholds


def load_thresholds(path: Path | None = None) -> Thresholds:
    raw = yaml.safe_load((path or _DEFAULT_PATH).read_text(encoding="utf-8"))
    return Thresholds.model_validate(raw)
