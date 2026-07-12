"""Hybrid retrieval: reciprocal rank fusion (RRF) of the lexical and dense arms.

RRF combines *ranks*, not raw scores, so BM25 scores (unbounded) and cosine
similarities ([-1, 1]) need no calibration against each other. It is fully
deterministic given the two ranked lists, which keeps the hybrid benchmark
inside the keyless CI gate when paired with the hashing embedder.
"""

from __future__ import annotations

from collections.abc import Sequence

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk
from requirements_audit.retrieval.dense import DenseIndex
from requirements_audit.retrieval.embedding import Embedder
from requirements_audit.retrieval.lexical import LexicalIndex, ScoredChunk

# The standard constant from Cormack et al.; dampens the gap between adjacent
# ranks so a document ranked well by *both* arms beats a single-arm #1.
_RRF_C = 60


def rrf_fuse(rankings: Sequence[Sequence[ScoredChunk]], k: int) -> list[ScoredChunk]:
    """Fuse ranked lists: score(d) = Σ over lists 1 / (C + rank_in_list(d)).

    Documents absent from a list simply contribute nothing for it. Ties break
    on requirement id so output order is deterministic.
    """
    scores: dict[str, float] = {}
    chunk_by_id: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            req_id = hit.chunk.requirement_id
            scores[req_id] = scores.get(req_id, 0.0) + 1.0 / (_RRF_C + rank)
            chunk_by_id.setdefault(req_id, hit.chunk)

    fused = [ScoredChunk(chunk=chunk_by_id[rid], score=score) for rid, score in scores.items()]
    fused.sort(key=lambda s: (-s.score, s.chunk.requirement_id))
    return fused[:k]


class HybridIndex:
    """BM25 + dense retrieval fused with RRF. Build once, query many times."""

    def __init__(self, lexical: LexicalIndex, dense: DenseIndex, fetch_depth: int = 20) -> None:
        # Each arm is queried deeper than the final k so fusion has enough
        # candidates for cross-arm agreement to surface.
        self._lexical = lexical
        self._dense = dense
        self._fetch_depth = fetch_depth

    @classmethod
    def from_store(cls, store: SqliteStore, embedder: Embedder) -> HybridIndex:
        chunks = store.all_chunks()
        return cls(LexicalIndex(chunks), DenseIndex(chunks, embedder))

    def search(self, query: str, k: int = 5) -> list[ScoredChunk]:
        depth = max(k, self._fetch_depth)
        return rrf_fuse(
            [self._lexical.search(query, depth), self._dense.search(query, depth)],
            k,
        )
