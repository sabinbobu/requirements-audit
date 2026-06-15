"""Lexical retrieval: a small, dependency-free Okapi BM25 over the stored chunks.

This is the *lexical arm* of what the architecture calls hybrid retrieval. The
dense-embedding arm and Qdrant fusion are deferred to Phase E (Benchmark), which
sweeps dense vs hybrid vs hybrid+rerank — so the tool keeps the name
`hybrid_search` while this implementation is lexical-only. Being pure-Python and
deterministic, it runs in CI with no services and no API keys.

# BENCH: Phase E replaces / augments this with dense + BM25 fusion over Qdrant.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from pydantic import BaseModel

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase word/number tokens. `watchdog_timeout_ms` -> watchdog, timeout, ms."""
    return _TOKEN.findall(text.lower())


def _chunk_terms(chunk: Chunk) -> list[str]:
    parts = [chunk.title, chunk.text, *chunk.parameters.keys(), *chunk.parameters.values()]
    return tokenize(" ".join(parts))


class ScoredChunk(BaseModel):
    chunk: Chunk
    score: float


class LexicalIndex:
    """An in-memory BM25 index. Build once, query many times (e.g. an audit sweep)."""

    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks
        self._terms: list[list[str]] = [_chunk_terms(c) for c in chunks]
        self._tf: list[Counter[str]] = [Counter(t) for t in self._terms]
        self._lengths = [len(t) for t in self._terms]
        self._avg_len = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0

        df: Counter[str] = Counter()
        for terms in self._terms:
            df.update(set(terms))
        n = len(chunks)
        # BM25+ idf, floored at 0 so common terms never push scores negative.
        self._idf = {
            term: max(0.0, math.log(1.0 + (n - freq + 0.5) / (freq + 0.5)))
            for term, freq in df.items()
        }

    @classmethod
    def from_store(cls, store: SqliteStore) -> LexicalIndex:
        return cls(store.all_chunks())

    def _score(self, query_terms: list[str], doc_idx: int) -> float:
        tf = self._tf[doc_idx]
        length = self._lengths[doc_idx]
        norm = _K1 * (1 - _B + _B * length / self._avg_len) if self._avg_len else _K1
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0)
            if f == 0:
                continue
            score += self._idf.get(term, 0.0) * (f * (_K1 + 1)) / (f + norm)
        return score

    def search(self, query: str, k: int = 5) -> list[ScoredChunk]:
        query_terms = tokenize(query)
        scored = [
            ScoredChunk(chunk=self._chunks[i], score=self._score(query_terms, i))
            for i in range(len(self._chunks))
        ]
        scored = [s for s in scored if s.score > 0.0]
        # Stable: score desc, then requirement id asc for determinism.
        scored.sort(key=lambda s: (-s.score, s.chunk.requirement_id))
        return scored[:k]


def search(store: SqliteStore, query: str, k: int = 5) -> list[ScoredChunk]:
    """Convenience one-shot search; builds a fresh index. For repeated queries,
    build a `LexicalIndex` once and reuse it."""
    return LexicalIndex.from_store(store).search(query, k)
