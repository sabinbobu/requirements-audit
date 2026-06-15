"""Deterministic audit tests — the gate-able, LLM-free contradiction recall.

These prove the candidate-generation layer without any model:
  * the numeric + superseded detectors recall every seeded conflict of those
    classes, and do not flag the near-misses;
  * the LLM-comparator candidate generator surfaces the four prose
    `incompatible_constraint` conflicts (C07-C10) within the pair budget.

The LLM's judgement of those prose pairs is exercised separately (test_agents),
and measured for real only on live/nightly runs.
"""

from __future__ import annotations

from requirements_audit.agents.audit import (
    _values_differ,
    detect_numeric_mismatches,
    detect_superseded_references,
    deterministic_candidates,
    incompatible_candidate_pairs,
)
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import ConflictType, Contradiction


def _pairs(candidates: object) -> set[frozenset[str]]:
    return {frozenset((c.req_a, c.req_b)) for c in candidates}  # type: ignore[attr-defined]


def _expected(contradictions: list[Contradiction], *types: ConflictType) -> set[frozenset[str]]:
    return {
        frozenset((c.req_a, c.req_b))
        for c in contradictions
        if c.is_true_conflict and c.conflict_type in types
    }


# ─── unit: value comparison ──────────────────────────────────────────────────
def test_values_differ() -> None:
    assert _values_differ("100", "250")
    assert _values_differ("9.0", "10.5")
    assert _values_differ("-40", "-20")
    assert not _values_differ("100", "100")
    assert not _values_differ("-40..85", "-40..85")
    assert not _values_differ("12", None)


# ─── deterministic recall (no LLM) ───────────────────────────────────────────
def test_numeric_detector_finds_all_numeric_conflicts(
    store: SqliteStore, contradictions: list[Contradiction]
) -> None:
    found = _pairs(detect_numeric_mismatches(store))
    expected = _expected(contradictions, ConflictType.NUMERIC_MISMATCH)
    assert expected <= found, expected - found


def test_superseded_detector_finds_all_superseded_conflicts(
    store: SqliteStore, contradictions: list[Contradiction]
) -> None:
    found = _pairs(detect_superseded_references(store))
    expected = _expected(contradictions, ConflictType.SUPERSEDED_REFERENCE)
    assert expected <= found, expected - found


def test_deterministic_recall_covers_numeric_and_superseded(
    store: SqliteStore, contradictions: list[Contradiction]
) -> None:
    found = _pairs(deterministic_candidates(store))
    gate_classes = _expected(
        contradictions, ConflictType.NUMERIC_MISMATCH, ConflictType.SUPERSEDED_REFERENCE
    )
    missing = gate_classes - found
    assert not missing, f"deterministic gate missed {missing}"


def test_deterministic_does_not_flag_near_misses(
    store: SqliteStore, near_miss_pairs: set[frozenset[str]]
) -> None:
    found = _pairs(deterministic_candidates(store))
    wrongly_flagged = near_miss_pairs & found
    assert not wrongly_flagged, wrongly_flagged


# ─── comparator candidate generation (deterministic; LLM judges later) ───────
def test_incompatible_pairs_surface_prose_conflicts(
    store: SqliteStore, contradictions: list[Contradiction]
) -> None:
    exclude: set[tuple[str, str]] = {
        (c.req_a, c.req_b) if c.req_a <= c.req_b else (c.req_b, c.req_a)
        for c in deterministic_candidates(store)
    }
    pairs = incompatible_candidate_pairs(store, max_pairs=60, exclude=exclude)
    surfaced = {frozenset((p.req_a, p.req_b)) for p in pairs}

    incompatible_true = _expected(contradictions, ConflictType.INCOMPATIBLE_CONSTRAINT)
    # C06 also shares a parameter, so it is caught (and excluded) deterministically;
    # the comparator must surface the remaining prose conflicts (C07-C10).
    prose_only = {p for p in incompatible_true if tuple(sorted(p)) not in exclude}
    missing = prose_only - surfaced
    assert not missing, f"comparator did not surface prose conflicts {missing}"
