"""Level-1 assertions — cheap, deterministic invariants run on every commit.

These are the format/shape/sanity checks Hamel calls L1: requirement-ID format,
ground-truth schema and counts, and threshold-config sanity. They cost nothing and
fail fast on the dumbest regressions.
"""

from __future__ import annotations

import re

import pytest

from requirements_audit.eval.thresholds import Thresholds
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Contradiction, GoldenQuestion

pytestmark = pytest.mark.eval

_REQ_ID = re.compile(r"^[A-Z]+-REQ-\d{4}$")


def test_all_requirement_ids_well_formed(store: SqliteStore) -> None:
    for chunk in store.all_chunks():
        assert _REQ_ID.match(chunk.requirement_id), chunk.requirement_id


def test_golden_set_schema_and_size(golden_questions: list[GoldenQuestion]) -> None:
    assert len(golden_questions) == 50
    assert all(q.id and q.question for q in golden_questions)
    # Every expected source id is well-formed when present.
    for q in golden_questions:
        for rid in q.expected_source_ids:
            assert _REQ_ID.match(rid), rid


def test_contradiction_ground_truth_counts(contradictions: list[Contradiction]) -> None:
    assert len(contradictions) == 20
    assert sum(c.is_true_conflict for c in contradictions) == 15


def test_thresholds_are_sane(thresholds: Thresholds) -> None:
    gate = thresholds.gate
    assert 0.0 <= gate.retrieval.precision_at_k <= 1.0
    assert 0.0 <= gate.retrieval.recall_at_k <= 1.0
    assert gate.retrieval.k > 0
    assert gate.deterministic_recall_min >= 0
    live = thresholds.live
    assert 0.0 <= live.generation.faithfulness_min <= 1.0
    assert live.contradiction.full_recall_min >= gate.deterministic_recall_min
