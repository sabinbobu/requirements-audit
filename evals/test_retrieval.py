"""Retrieval eval gate (deterministic, no keys) — runs on every commit."""

from __future__ import annotations

import pytest

from requirements_audit.eval.retrieval import (
    evaluate_retrieval,
    precision_at_k,
    recall_at_k,
)
from requirements_audit.eval.thresholds import Thresholds
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion

pytestmark = pytest.mark.eval


def test_precision_recall_primitives() -> None:
    expected = {"A", "B"}
    retrieved = ["A", "X", "B", "Y", "Z"]
    assert precision_at_k(expected, retrieved, 5) == pytest.approx(2 / 5)
    assert recall_at_k(expected, retrieved, 5) == pytest.approx(1.0)
    assert recall_at_k(expected, retrieved, 1) == pytest.approx(0.5)


def test_retrieval_meets_gate_thresholds(
    store: SqliteStore, golden_questions: list[GoldenQuestion], thresholds: Thresholds
) -> None:
    gate = thresholds.gate.retrieval
    score = evaluate_retrieval(store, golden_questions, gate.k)
    assert score.n_questions > 0
    assert score.recall_at_k >= gate.recall_at_k, score.model_dump()
    assert score.precision_at_k >= gate.precision_at_k, score.model_dump()
