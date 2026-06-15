"""Retrieval metrics: precision@k / recall@k on the golden set.

Deterministic (BM25, no LLM), so these run in the every-commit eval gate. Only
golden questions that carry `expected_source_ids` are scored — the no_result /
missing_data / permission_edge scenarios have no relevant source by construction
and are handled by the L1 abstention assertions instead.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion
from requirements_audit.retrieval.lexical import LexicalIndex


def precision_at_k(expected: set[str], retrieved: Sequence[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    return len(expected & set(top)) / k


def recall_at_k(expected: set[str], retrieved: Sequence[str], k: int) -> float:
    if not expected:
        return 0.0
    top = set(retrieved[:k])
    return len(expected & top) / len(expected)


class RetrievalScore(BaseModel):
    precision_at_k: float
    recall_at_k: float
    k: int
    n_questions: int


def evaluate_retrieval(
    store: SqliteStore, questions: Sequence[GoldenQuestion], k: int
) -> RetrievalScore:
    """Mean precision@k / recall@k over questions that have expected sources."""
    index = LexicalIndex.from_store(store)
    scored = [q for q in questions if q.expected_source_ids]
    if not scored:
        return RetrievalScore(precision_at_k=0.0, recall_at_k=0.0, k=k, n_questions=0)

    p_total = r_total = 0.0
    for q in scored:
        retrieved = [hit.chunk.requirement_id for hit in index.search(q.question, k)]
        expected = set(q.expected_source_ids)
        p_total += precision_at_k(expected, retrieved, k)
        r_total += recall_at_k(expected, retrieved, k)

    n = len(scored)
    return RetrievalScore(precision_at_k=p_total / n, recall_at_k=r_total / n, k=k, n_questions=n)
