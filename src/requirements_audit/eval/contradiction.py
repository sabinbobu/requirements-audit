"""Contradiction-detection metrics against the seeded ground truth.

Given a set of found requirement pairs, score precision / recall / false-positive
rate against the 15 true conflicts and 5 near-misses. The same function scores the
deterministic candidate set (gate) and the full pipeline output before vs after the
Critic (live) — that delta is the "before/after Critic" precision lift.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel

from requirements_audit.models import Contradiction

Pair = frozenset[str]


class GroundTruthPairs(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    true_pairs: set[Pair]
    near_miss_pairs: set[Pair]

    @classmethod
    def from_contradictions(cls, contradictions: Iterable[Contradiction]) -> GroundTruthPairs:
        true_pairs: set[Pair] = set()
        near: set[Pair] = set()
        for c in contradictions:
            (true_pairs if c.is_true_conflict else near).add(frozenset((c.req_a, c.req_b)))
        return cls(true_pairs=true_pairs, near_miss_pairs=near)


class ContradictionScore(BaseModel):
    precision: float
    recall: float
    false_positive_rate: float  # near-misses wrongly flagged / total near-misses
    true_positives: int
    found: int
    total_true: int


def score(found_pairs: Iterable[Pair], gt: GroundTruthPairs) -> ContradictionScore:
    found = set(found_pairs)
    tp = found & gt.true_pairs
    precision = len(tp) / len(found) if found else 0.0
    recall = len(tp) / len(gt.true_pairs) if gt.true_pairs else 0.0
    fp_near = found & gt.near_miss_pairs
    fp_rate = len(fp_near) / len(gt.near_miss_pairs) if gt.near_miss_pairs else 0.0
    return ContradictionScore(
        precision=precision,
        recall=recall,
        false_positive_rate=fp_rate,
        true_positives=len(tp),
        found=len(found),
        total_true=len(gt.true_pairs),
    )


def pairs_from(candidates: Iterable[object]) -> set[Pair]:
    """Collect req_a/req_b pairs from anything exposing those attributes
    (CandidateContradiction or Finding.candidate)."""
    out: set[Pair] = set()
    for c in candidates:
        out.add(frozenset((getattr(c, "req_a"), getattr(c, "req_b"))))  # noqa: B009
    return out
