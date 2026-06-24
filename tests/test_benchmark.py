"""Phase E benchmark harness tests."""

from __future__ import annotations

import json

from requirements_audit.corpus.generator import build_golden_set
from requirements_audit.eval.benchmark import (
    BenchmarkStatus,
    RetrievalStrategy,
    run_retrieval_benchmark,
    write_report,
)
from requirements_audit.ingestion.store import SqliteStore


def test_retrieval_benchmark_measures_lexical_baseline(store: SqliteStore) -> None:
    report = run_retrieval_benchmark(
        store, build_golden_set(), strategies=[RetrievalStrategy.LEXICAL]
    )

    assert len(report.retrieval) == 1
    result = report.retrieval[0]
    assert result.strategy is RetrievalStrategy.LEXICAL
    assert result.status is BenchmarkStatus.MEASURED
    assert result.n_questions > 0
    assert result.precision_at_k is not None
    assert result.recall_at_k is not None


def test_retrieval_benchmark_marks_unimplemented_variants(store: SqliteStore) -> None:
    report = run_retrieval_benchmark(
        store,
        build_golden_set(),
        strategies=[RetrievalStrategy.LEXICAL, RetrievalStrategy.HYBRID_RERANK],
    )

    rerank = report.retrieval[1]
    assert rerank.strategy is RetrievalStrategy.HYBRID_RERANK
    assert rerank.status is BenchmarkStatus.NOT_IMPLEMENTED
    assert rerank.precision_at_k is None
    assert "planned" in rerank.note


def test_write_report_creates_json(tmp_path, store: SqliteStore) -> None:  # type: ignore[no-untyped-def]
    report = run_retrieval_benchmark(store, build_golden_set())
    path = tmp_path / "benchmark.json"

    write_report(report, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["retrieval"][0]["strategy"] == "lexical"
