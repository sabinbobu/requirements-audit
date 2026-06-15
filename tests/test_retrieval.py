"""Lexical retrieval smoke tests — deterministic, no LLM, run on every commit.

Proves BM25 returns sane chunks for the hand-picked anchor questions (Phase B
"done means": smoke retrieval returns sane chunks for hand-picked questions).
"""

from __future__ import annotations

import pytest

from requirements_audit.corpus import spec
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.retrieval.lexical import LexicalIndex, search, tokenize


def test_tokenize_splits_identifiers() -> None:
    assert tokenize("watchdog_timeout_ms = 100") == ["watchdog", "timeout", "ms", "100"]


def test_search_ranks_relevant_requirement_first(store: SqliteStore) -> None:
    hits = search(store, "watchdog supervision timeout", k=5)
    assert hits, "expected at least one hit"
    top_ids = {h.chunk.requirement_id for h in hits}
    # Both watchdog-timeout requirements should surface for this query.
    assert "SYS-REQ-0101" in top_ids
    assert all(h.score > 0 for h in hits)


def test_no_match_returns_empty(store: SqliteStore) -> None:
    assert search(store, "zzzqqq nonexistent vocabulary", k=5) == []


@pytest.mark.parametrize(
    ("question", "expected_id"),
    [(a.question, a.requirement.id) for a in spec.ANCHORS],
)
def test_anchor_questions_retrieve_their_requirement(
    store: SqliteStore, question: str, expected_id: str
) -> None:
    """Each clean anchor question retrieves its own requirement in the top 5."""
    index = LexicalIndex.from_store(store)
    hits = index.search(question, k=5)
    assert expected_id in {h.chunk.requirement_id for h in hits}, question
