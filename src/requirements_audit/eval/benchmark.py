"""Phase E benchmark harness.

Measured strategies: the deterministic BM25 baseline, the dense arm (in-process
Qdrant + a pluggable embedder), and hybrid RRF fusion of the two. Reranking is
still represented explicitly as `not_implemented` so benchmark output shows what
does not exist yet instead of silently substituting a weaker variant.

Each measured row's `note` names the embedder that produced it: the keyless CI
run uses the deterministic hashing embedder (a wiring floor), the live/nightly
run uses OpenAI embeddings — the two must never be confused in the README table.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from requirements_audit.eval.retrieval import evaluate_retrieval
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion
from requirements_audit.retrieval.dense import DenseIndex
from requirements_audit.retrieval.embedding import Embedder, HashingEmbedder
from requirements_audit.retrieval.fusion import HybridIndex
from requirements_audit.retrieval.lexical import LexicalIndex


class RetrievalStrategy(StrEnum):
    LEXICAL = "lexical"
    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class BenchmarkStatus(StrEnum):
    MEASURED = "measured"
    NOT_IMPLEMENTED = "not_implemented"


class RetrievalBenchmarkResult(BaseModel):
    strategy: RetrievalStrategy
    status: BenchmarkStatus
    k: int
    n_questions: int
    precision_at_k: float | None = None
    recall_at_k: float | None = None
    note: str = ""


class BenchmarkReport(BaseModel):
    retrieval: list[RetrievalBenchmarkResult]


_NOT_IMPLEMENTED_NOTES: dict[RetrievalStrategy, str] = {
    RetrievalStrategy.HYBRID_RERANK: (
        "Reranking is planned as the next increment now that hybrid fusion is measured."
    ),
}


def load_golden_questions(path: Path) -> list[GoldenQuestion]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenQuestion(**q) for q in raw]


def run_retrieval_benchmark(
    store: SqliteStore,
    questions: list[GoldenQuestion],
    *,
    strategies: list[RetrievalStrategy] | None = None,
    k: int = 5,
    embedder: Embedder | None = None,
) -> BenchmarkReport:
    """Score each selected strategy on the golden set with identical metric code.

    `embedder` powers the dense/hybrid strategies; when None the deterministic
    hashing embedder is used so the benchmark stays runnable with no keys.
    """
    selected = strategies or [RetrievalStrategy.LEXICAL]
    results: list[RetrievalBenchmarkResult] = []

    chunks = store.all_chunks()
    # Indexes are built lazily and shared across strategies: the dense index in
    # particular embeds the whole corpus, which costs real API calls when a
    # non-hashing embedder is in play.
    lexical_index: LexicalIndex | None = None
    dense_index: DenseIndex | None = None

    def _lexical() -> LexicalIndex:
        nonlocal lexical_index
        if lexical_index is None:
            lexical_index = LexicalIndex(chunks)
        return lexical_index

    def _dense() -> tuple[DenseIndex, Embedder]:
        nonlocal dense_index, embedder
        if embedder is None:
            embedder = HashingEmbedder()
        if dense_index is None:
            dense_index = DenseIndex(chunks, embedder)
        return dense_index, embedder

    for strategy in selected:
        if strategy is RetrievalStrategy.HYBRID_RERANK:
            results.append(
                RetrievalBenchmarkResult(
                    strategy=strategy,
                    status=BenchmarkStatus.NOT_IMPLEMENTED,
                    k=k,
                    n_questions=0,
                    note=_NOT_IMPLEMENTED_NOTES[strategy],
                )
            )
            continue

        if strategy is RetrievalStrategy.LEXICAL:
            index: LexicalIndex | DenseIndex | HybridIndex = _lexical()
            note = "BM25 lexical baseline over SQLite chunks."
        elif strategy is RetrievalStrategy.DENSE:
            index, emb = _dense()
            note = f"Dense cosine retrieval over in-process Qdrant; embedder={emb.name}."
        else:  # HYBRID
            d_index, emb = _dense()
            index = HybridIndex(_lexical(), d_index)
            note = f"RRF fusion of BM25 + dense arms; embedder={emb.name}."

        score = evaluate_retrieval(store, questions, k, index=index)
        results.append(
            RetrievalBenchmarkResult(
                strategy=strategy,
                status=BenchmarkStatus.MEASURED,
                k=score.k,
                n_questions=score.n_questions,
                precision_at_k=score.precision_at_k,
                recall_at_k=score.recall_at_k,
                note=note,
            )
        )

    return BenchmarkReport(retrieval=results)


def write_report(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
