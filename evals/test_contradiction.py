"""Contradiction-detection eval.

Gate (deterministic, no keys): the rule-based candidates recover the numeric +
superseded conflicts and flag no near-misses.

Live (skipped without keys): the full pipeline recovers >= the recall floor, and
the Critic lifts precision above its floor — the "before vs after Critic" metric.
"""

from __future__ import annotations

import pytest

from requirements_audit.agents.audit import deterministic_candidates
from requirements_audit.config import Settings
from requirements_audit.eval.contradiction import GroundTruthPairs, pairs_from, score
from requirements_audit.eval.thresholds import Thresholds
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.orchestrator import run_audit

pytestmark = pytest.mark.eval


def test_deterministic_contradiction_gate(
    store: SqliteStore, gt_pairs: GroundTruthPairs, thresholds: Thresholds
) -> None:
    found = pairs_from(deterministic_candidates(store))
    result = score(found, gt_pairs)
    assert result.true_positives >= thresholds.gate.deterministic_recall_min, result.model_dump()
    assert result.false_positive_rate == 0.0, "deterministic rules flagged a near-miss"


def test_full_pipeline_recall_and_critic_precision(
    store: SqliteStore,
    gt_pairs: GroundTruthPairs,
    thresholds: Thresholds,
    live_model: object,
) -> None:
    """Live: full hybrid audit meets the recall floor; precision clears the Critic floor."""
    settings = Settings()
    report, _trace = run_audit(store, settings, model=live_model, use_llm=True)  # type: ignore[arg-type]
    found = pairs_from(f.candidate for f in report.findings)
    result = score(found, gt_pairs)
    live = thresholds.live.contradiction
    assert result.true_positives >= live.full_recall_min, result.model_dump()
    assert result.precision >= live.critic_precision_min, result.model_dump()
