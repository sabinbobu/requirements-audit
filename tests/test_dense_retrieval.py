"""Dense arm + hybrid fusion tests — deterministic (hashing embedder, no keys)."""

from __future__ import annotations

import math

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk
from requirements_audit.retrieval.dense import DenseIndex
from requirements_audit.retrieval.embedding import HashingEmbedder
from requirements_audit.retrieval.fusion import HybridIndex, rrf_fuse
from requirements_audit.retrieval.lexical import LexicalIndex, ScoredChunk


def _chunk(req_id: str, title: str, text: str) -> Chunk:
    """A minimal chunk for index tests; only retrieval-relevant fields vary."""
    return Chunk(
        id=f"doc-{req_id}",
        doc_id="DOC",
        requirement_id=req_id,
        section_path=["1"],
        title=title,
        text=text,
        content_hash="x",
    )


# Three chunks with disjoint vocabularies so ranking assertions are unambiguous.
_CHUNKS = [
    _chunk("REQ-001", "Watchdog timeout", "The watchdog timer shall expire after 50 ms."),
    _chunk("REQ-002", "CAN bus bitrate", "The CAN bus shall operate at 500 kbit per second."),
    _chunk("REQ-003", "Display brightness", "The display brightness shall be adjustable."),
]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


# ─── HashingEmbedder ──────────────────────────────────────────────────────────
def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    emb = HashingEmbedder()
    [v1], [v2] = emb.embed(["watchdog timeout 50 ms"]), emb.embed(["watchdog timeout 50 ms"])
    assert v1 == v2  # blake2b hashing → identical vectors across calls/processes
    assert len(v1) == emb.dim
    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-9)


def test_hashing_embedder_similarity_tracks_token_overlap() -> None:
    emb = HashingEmbedder()
    query, related, unrelated = emb.embed(
        ["watchdog timer expiry", "watchdog timer shall expire", "display brightness adjustable"]
    )
    assert _cosine(query, related) > _cosine(query, unrelated)


def test_hashing_embedder_featureless_text_gives_zero_vector() -> None:
    [v] = HashingEmbedder().embed(["→ … —"])  # no [a-z0-9] tokens at all
    assert not any(v)


# ─── DenseIndex ───────────────────────────────────────────────────────────────
def test_dense_index_ranks_matching_vocabulary_first() -> None:
    index = DenseIndex(_CHUNKS, HashingEmbedder())
    hits = index.search("watchdog timer expiry", k=3)
    assert hits, "expected at least one hit"
    assert hits[0].chunk.requirement_id == "REQ-001"
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_dense_index_featureless_query_returns_nothing() -> None:
    index = DenseIndex(_CHUNKS, HashingEmbedder())
    assert index.search("→ … —", k=3) == []


def test_dense_index_empty_corpus_returns_nothing() -> None:
    index = DenseIndex([], HashingEmbedder())
    assert index.search("watchdog", k=3) == []


# ─── RRF fusion ───────────────────────────────────────────────────────────────
def test_rrf_fusion_prefers_cross_arm_agreement() -> None:
    a, b, c = _CHUNKS
    # `a` is ranked (second) by BOTH arms; b and c each top only one arm.
    lexical = [ScoredChunk(chunk=b, score=9.0), ScoredChunk(chunk=a, score=5.0)]
    dense = [ScoredChunk(chunk=c, score=0.9), ScoredChunk(chunk=a, score=0.5)]
    fused = rrf_fuse([lexical, dense], k=3)
    assert fused[0].chunk.requirement_id == a.requirement_id


def test_rrf_fusion_ties_break_on_requirement_id() -> None:
    a, b, _ = _CHUNKS
    # Symmetric ranks → identical RRF scores; order must fall back to req id.
    fused = rrf_fuse(
        [[ScoredChunk(chunk=b, score=1.0)], [ScoredChunk(chunk=a, score=1.0)]],
        k=2,
    )
    assert [f.chunk.requirement_id for f in fused] == ["REQ-001", "REQ-002"]


# ─── HybridIndex over the real corpus ─────────────────────────────────────────
def test_hybrid_index_searches_ingested_corpus(store: SqliteStore) -> None:
    hybrid = HybridIndex.from_store(store, HashingEmbedder())
    hits = hybrid.search("watchdog timeout", k=5)
    assert 0 < len(hits) <= 5
    # Deterministic end to end: a second identical index gives the same ranking.
    again = HybridIndex.from_store(store, HashingEmbedder()).search("watchdog timeout", k=5)
    assert [h.chunk.requirement_id for h in hits] == [h.chunk.requirement_id for h in again]


def test_hybrid_matches_arms_on_their_common_top_hit() -> None:
    chunks = _CHUNKS
    hybrid = HybridIndex(LexicalIndex(chunks), DenseIndex(chunks, HashingEmbedder()))
    hits = hybrid.search("CAN bus bitrate", k=3)
    assert hits[0].chunk.requirement_id == "REQ-002"
