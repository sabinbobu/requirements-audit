"""Term-coverage reranker tests — deterministic, no keys."""

from __future__ import annotations

from requirements_audit.models import Chunk
from requirements_audit.retrieval.dense import DenseIndex
from requirements_audit.retrieval.embedding import HashingEmbedder
from requirements_audit.retrieval.fusion import HybridIndex
from requirements_audit.retrieval.lexical import LexicalIndex, ScoredChunk
from requirements_audit.retrieval.rerank import RerankingIndex, rerank


def _chunk(req_id: str, title: str, text: str) -> Chunk:
    return Chunk(
        id=f"doc-{req_id}",
        doc_id="DOC",
        requirement_id=req_id,
        section_path=["1"],
        title=title,
        text=text,
        content_hash="x",
    )


def test_rerank_promotes_full_coverage_over_term_frequency() -> None:
    """The exact failure mode reranking exists for: a chunk repeating one query
    word must lose to a chunk containing every query word once."""
    repeat = _chunk("REQ-101", "Watchdog", "watchdog watchdog watchdog watchdog watchdog")
    covers = _chunk("REQ-102", "Watchdog timeout", "The watchdog timeout is 50 ms.")
    # Simulate hybrid output where term frequency put `repeat` first.
    candidates = [ScoredChunk(chunk=repeat, score=9.0), ScoredChunk(chunk=covers, score=5.0)]

    reranked = rerank("watchdog timeout ms", candidates, k=2)

    assert reranked[0].chunk.requirement_id == "REQ-102"
    assert reranked[0].score == 1.0  # full coverage of the three query terms


def test_rerank_falls_back_to_fused_score_on_equal_coverage() -> None:
    a = _chunk("REQ-201", "CAN bitrate", "The CAN bus operates at 500 kbit.")
    b = _chunk("REQ-202", "CAN bitrate copy", "The CAN bus also operates at 500 kbit.")
    candidates = [ScoredChunk(chunk=b, score=3.0), ScoredChunk(chunk=a, score=7.0)]

    reranked = rerank("CAN bitrate", candidates, k=2)

    # Equal coverage → the higher fused score (a) wins.
    assert [r.chunk.requirement_id for r in reranked] == ["REQ-201", "REQ-202"]


def test_rerank_featureless_query_keeps_fused_order() -> None:
    a = _chunk("REQ-301", "Alpha", "alpha")
    b = _chunk("REQ-302", "Beta", "beta")
    candidates = [ScoredChunk(chunk=a, score=2.0), ScoredChunk(chunk=b, score=1.0)]

    reranked = rerank("→ … —", candidates, k=2)  # no query terms → coverage all 0

    assert [r.chunk.requirement_id for r in reranked] == ["REQ-301", "REQ-302"]


def test_reranking_index_is_deterministic_over_corpus() -> None:
    chunks = [
        _chunk("REQ-001", "Watchdog timeout", "The watchdog timer shall expire after 50 ms."),
        _chunk("REQ-002", "CAN bus bitrate", "The CAN bus shall operate at 500 kbit per second."),
        _chunk("REQ-003", "Display brightness", "The display brightness shall be adjustable."),
    ]

    def build() -> RerankingIndex:
        return RerankingIndex(HybridIndex(LexicalIndex(chunks), DenseIndex(chunks, HashingEmbedder())))

    first = build().search("watchdog timer expiry", k=3)
    second = build().search("watchdog timer expiry", k=3)

    assert first, "expected hits"
    assert first[0].chunk.requirement_id == "REQ-001"
    assert [h.chunk.requirement_id for h in first] == [h.chunk.requirement_id for h in second]
