"""Phase E benchmark harness.

The first measured strategy is the existing deterministic BM25 retriever. Dense,
hybrid, and rerank variants are represented explicitly so benchmark output shows
what has not been implemented yet instead of silently substituting BM25.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from requirements_audit.eval.retrieval import evaluate_retrieval
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import GoldenQuestion


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
    RetrievalStrategy.DENSE: "Dense embeddings and Qdrant vector search are planned next.",
    RetrievalStrategy.HYBRID: "Hybrid dense+BM25 fusion is planned after dense retrieval lands.",
    RetrievalStrategy.HYBRID_RERANK: "Reranking is planned after hybrid fusion has a measured baseline.",
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
) -> BenchmarkReport:
    selected = strategies or [RetrievalStrategy.LEXICAL]
    results: list[RetrievalBenchmarkResult] = []

    for strategy in selected:
        if strategy is RetrievalStrategy.LEXICAL:
            score = evaluate_retrieval(store, questions, k)
            results.append(
                RetrievalBenchmarkResult(
                    strategy=strategy,
                    status=BenchmarkStatus.MEASURED,
                    k=score.k,
                    n_questions=score.n_questions,
                    precision_at_k=score.precision_at_k,
                    recall_at_k=score.recall_at_k,
                    note="BM25 lexical baseline over SQLite chunks.",
                )
            )
            continue

        results.append(
            RetrievalBenchmarkResult(
                strategy=strategy,
                status=BenchmarkStatus.NOT_IMPLEMENTED,
                k=k,
                n_questions=0,
                note=_NOT_IMPLEMENTED_NOTES[strategy],
            )
        )

    return BenchmarkReport(retrieval=results)


def write_report(report: BenchmarkReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
