"""Reranking: reorder hybrid candidates by query-term coverage.

BM25 and RRF both reward high term *frequency*; a chunk that repeats one query
word can outrank a chunk that mentions every query word once. The reranker
fixes exactly that failure mode: it re-sorts the top candidates by the fraction
of distinct query terms they contain, falling back to the fused score to break
ties. It is pure-Python and deterministic, so the `hybrid_rerank` benchmark row
stays inside the keyless CI gate.

This is deliberately the *simplest real reranker* — a cross-encoder or LLM
reranker is the live-run upgrade path, and the benchmark note discloses which
one produced any given number.
"""

from __future__ import annotations

from requirements_audit.retrieval.fusion import HybridIndex
from requirements_audit.retrieval.lexical import ScoredChunk, tokenize

RERANKER_NAME = "term-coverage"


def _coverage(query_terms: set[str], chunk: ScoredChunk) -> float:
    """Fraction of distinct query terms present in the chunk's title/text/params."""
    if not query_terms:
        return 0.0
    haystack = set(
        tokenize(
            " ".join(
                [
                    chunk.chunk.title,
                    chunk.chunk.text,
                    *chunk.chunk.parameters.keys(),
                    *chunk.chunk.parameters.values(),
                ]
            )
        )
    )
    return len(query_terms & haystack) / len(query_terms)


def rerank(query: str, candidates: list[ScoredChunk], k: int) -> list[ScoredChunk]:
    """Re-sort candidates by (coverage desc, fused score desc, req id asc).

    The returned `score` is the coverage value so downstream consumers see what
    the ranking was actually decided by.
    """
    query_terms = set(tokenize(query))
    ranked = sorted(
        candidates,
        key=lambda c: (-_coverage(query_terms, c), -c.score, c.chunk.requirement_id),
    )
    return [
        ScoredChunk(chunk=c.chunk, score=_coverage(query_terms, c)) for c in ranked[:k]
    ]


class RerankingIndex:
    """Hybrid retrieval + term-coverage rerank. Build once, query many times.

    Pulls `fetch_depth` candidates from the hybrid index (deeper than the final
    k, so reranking has real material to reorder) and re-sorts them.
    """

    def __init__(self, hybrid: HybridIndex, fetch_depth: int = 20) -> None:
        self._hybrid = hybrid
        self._fetch_depth = fetch_depth

    def search(self, query: str, k: int = 5) -> list[ScoredChunk]:
        candidates = self._hybrid.search(query, max(k, self._fetch_depth))
        return rerank(query, candidates, k)
