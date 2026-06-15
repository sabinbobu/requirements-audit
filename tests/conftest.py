"""Shared fixtures: an ingested in-memory store and the contradiction ground truth."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from requirements_audit.ingestion.pipeline import ingest_corpus
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Contradiction

_ROOT = Path(__file__).resolve().parents[1]
_CORPUS = _ROOT / "corpus"
_CONTRADICTIONS = _ROOT / "evals" / "contradictions.json"


@pytest.fixture
def store() -> Iterator[SqliteStore]:
    """A fresh in-memory store with the full corpus ingested."""
    with SqliteStore(":memory:") as s:
        ingest_corpus(_CORPUS, s)
        yield s


@pytest.fixture(scope="session")
def contradictions() -> list[Contradiction]:
    raw = json.loads(_CONTRADICTIONS.read_text(encoding="utf-8"))
    return [Contradiction(**c) for c in raw]


@pytest.fixture(scope="session")
def true_pairs(contradictions: list[Contradiction]) -> set[frozenset[str]]:
    return {frozenset((c.req_a, c.req_b)) for c in contradictions if c.is_true_conflict}


@pytest.fixture(scope="session")
def near_miss_pairs(contradictions: list[Contradiction]) -> set[frozenset[str]]:
    return {frozenset((c.req_a, c.req_b)) for c in contradictions if not c.is_true_conflict}
