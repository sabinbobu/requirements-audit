"""Candidate generation for the audit path.

Two deterministic detectors (no LLM, gate-able in CI) cover the conflict classes
that have a clean signal:

  * `numeric_mismatch`     — two requirements share a parameter name but state
                             different values.
  * `superseded_reference` — a requirement references a target whose status is
                             `superseded`.

The third class, `incompatible_constraint`, is prose/semantic (e.g. "single
controller" vs "dual redundant channels") and has no rule signal — see the design
doc. For it we generate candidate *pairs* deterministically (cross-document
lexical neighbours) and let an LLM comparator judge each pair. The Critic then
verifies every surfaced candidate against quoted sources and rejects false
positives.

Integrity: nothing here reads `evals/contradictions.json`. Candidates come only
from stored chunk/entity data.
"""

from __future__ import annotations

import math
from collections import Counter
from itertools import combinations

from pydantic import BaseModel

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import (
    CandidateContradiction,
    ConflictType,
    RequirementStatus,
)
from requirements_audit.retrieval.lexical import tokenize


# ─── deterministic detectors ──────────────────────────────────────────────────
def _values_differ(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    fa, fb = _as_float(a), _as_float(b)
    if fa is not None and fb is not None:
        return not math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-9)
    return a.strip() != b.strip()


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _ordered(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def detect_numeric_mismatches(store: SqliteStore) -> list[CandidateContradiction]:
    """Pairs of requirements that share a parameter name but state different values."""
    by_name: dict[str, list[tuple[str, str | None]]] = {}
    for e in store.parameter_entities():
        by_name.setdefault(e.name, []).append((e.requirement_id, e.value))

    seen: set[tuple[str, str]] = set()
    candidates: list[CandidateContradiction] = []
    for entries in by_name.values():
        for (req_a, val_a), (req_b, val_b) in combinations(entries, 2):
            if req_a == req_b or not _values_differ(val_a, val_b):
                continue
            key = _ordered(req_a, req_b)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                _build(store, key[0], key[1], ConflictType.NUMERIC_MISMATCH, "numeric_rule")
            )
    return candidates


def detect_superseded_references(store: SqliteStore) -> list[CandidateContradiction]:
    """References whose target requirement has been superseded."""
    candidates: list[CandidateContradiction] = []
    seen: set[tuple[str, str]] = set()
    for ref in store.all_refs():
        if not ref.resolved:
            continue
        target = store.chunk(ref.to_req)
        if target is None or target.status is not RequirementStatus.SUPERSEDED:
            continue
        key = (ref.from_req, ref.to_req)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            _build(
                store,
                ref.from_req,
                ref.to_req,
                ConflictType.SUPERSEDED_REFERENCE,
                "superseded_rule",
            )
        )
    return candidates


def deterministic_candidates(store: SqliteStore) -> list[CandidateContradiction]:
    """All LLM-free candidates — the gate-able recall stage."""
    return detect_numeric_mismatches(store) + detect_superseded_references(store)


def _build(
    store: SqliteStore, req_a: str, req_b: str, conflict_type: ConflictType, source: str
) -> CandidateContradiction:
    ca, cb = store.chunk(req_a), store.chunk(req_b)
    return CandidateContradiction(
        req_a=req_a,
        req_b=req_b,
        conflict_type=conflict_type,
        evidence_quote_a=ca.text if ca else "",
        evidence_quote_b=cb.text if cb else "",
        source=source,
    )


# ─── candidate pairs for the LLM comparator (incompatible_constraint) ─────────
class ChunkPair(BaseModel):
    """A cross-document requirement pair handed to the LLM comparator."""

    req_a: str
    req_b: str
    text_a: str
    text_b: str


def incompatible_candidate_pairs(
    store: SqliteStore,
    *,
    rare_df: int = 4,
    max_pairs: int = 60,
    exclude: set[tuple[str, str]] | None = None,
) -> list[ChunkPair]:
    """Cross-document candidate pairs for the prose-conflict (incompatible) class.

    Full-text similarity is a poor signal here: the corpus filler is templated and
    self-similar, so BM25 buries the real conflicts. Instead we pair requirements
    that share a *rare* term — a term occurring in at most `rare_df` requirements —
    which is what links e.g. "redundant"/"channel" or "authentication"/"session"
    while ignoring boilerplate. Pairs are ranked by summed term rarity (1/df) so the
    most distinctive pairs survive the `max_pairs` cap. Deterministic; no LLM.

    Pairs already explained by a deterministic detector (`exclude`) are dropped.
    Near-miss pairs that slip through are intentionally left for the comparator and
    Critic to reject — that is the false-positive-filtering story.
    """
    exclude = exclude or set()
    chunks = store.all_chunks()
    terms = {c.requirement_id: set(tokenize(f"{c.title} {c.text}")) for c in chunks}
    doc_of = {c.requirement_id: c.doc_id for c in chunks}

    df: Counter[str] = Counter()
    for token_set in terms.values():
        df.update(token_set)

    inverted: dict[str, list[str]] = {}
    for req_id, token_set in terms.items():
        for term in token_set:
            if not term.isdigit() and df[term] <= rare_df:
                inverted.setdefault(term, []).append(req_id)

    weights: dict[tuple[str, str], float] = {}
    for term, req_ids in inverted.items():
        weight = 1.0 / df[term]
        for req_a, req_b in combinations(sorted(set(req_ids)), 2):
            if doc_of[req_a] == doc_of[req_b]:
                continue
            key = _ordered(req_a, req_b)
            if key in exclude:
                continue
            weights[key] = weights.get(key, 0.0) + weight

    ranked = sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))
    pairs: list[ChunkPair] = []
    for (req_a, req_b), _weight in ranked[:max_pairs]:
        left, right = store.chunk(req_a), store.chunk(req_b)
        if left is None or right is None:
            continue
        pairs.append(ChunkPair(req_a=req_a, req_b=req_b, text_a=left.text, text_b=right.text))
    return pairs
