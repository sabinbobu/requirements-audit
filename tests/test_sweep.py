"""Chunk-size sweep tests — deterministic (BM25 only, no keys)."""

from __future__ import annotations

from requirements_audit.corpus.generator import build_golden_set
from requirements_audit.eval.benchmark import BenchmarkStatus
from requirements_audit.eval.sweep import PER_REQUIREMENT, merge_chunks, run_chunk_sweep
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk
from requirements_audit.retrieval.lexical import tokenize


def _chunk(req_id: str, doc: str, section: str, text: str) -> Chunk:
    return Chunk(
        id=req_id,
        doc_id=doc,
        requirement_id=req_id,
        section_path=[doc, section],
        title=f"Title {req_id}",
        text=text,
        content_hash="x",
    )


def test_merge_respects_token_budget_and_covers_everything() -> None:
    chunks = [_chunk(f"REQ-{i:03d}", "DOC", "S1", "alpha beta gamma delta") for i in range(6)]

    merged = merge_chunks(chunks, max_tokens=14)  # each member ≈ 6 tokens (title + text)

    # Every requirement appears in exactly one merged chunk.
    all_covered = [rid for ids in merged.covered.values() for rid in ids]
    assert sorted(all_covered) == [c.requirement_id for c in chunks]
    # No group exceeds the budget (single oversized requirements are allowed).
    for chunk in merged.chunks:
        members = merged.covered[chunk.id]
        if len(members) > 1:
            assert len(tokenize(chunk.text)) <= 14 + len(members) * 2  # params/join slack


def test_merge_never_crosses_section_boundaries() -> None:
    chunks = [
        _chunk("REQ-001", "DOC", "S1", "one"),
        _chunk("REQ-002", "DOC", "S1", "two"),
        _chunk("REQ-003", "DOC", "S2", "three"),  # new section → new group
    ]

    merged = merge_chunks(chunks, max_tokens=1000)

    groups = [set(ids) for ids in merged.covered.values()]
    assert {"REQ-001", "REQ-002"} in groups
    assert {"REQ-003"} in groups


def test_oversized_requirement_still_gets_its_own_chunk() -> None:
    big = _chunk("REQ-BIG", "DOC", "S1", " ".join(f"word{i}" for i in range(100)))

    merged = merge_chunks([big], max_tokens=10)

    assert len(merged.chunks) == 1
    assert merged.covered[merged.chunks[0].id] == ["REQ-BIG"]


def test_chunk_sweep_reports_baseline_plus_each_size(store: SqliteStore) -> None:
    report = run_chunk_sweep(store, build_golden_set(), sizes=[256, 512], k=5)

    assert [r.chunk_size for r in report.sweep] == [PER_REQUIREMENT, 256, 512]
    baseline, *merged_rows = report.sweep
    assert baseline.n_chunks == store.chunk_count()
    for row in report.sweep:
        assert row.status is BenchmarkStatus.MEASURED
        assert row.n_questions > 0
        assert 0.0 <= row.precision_at_k <= 1.0
        assert 0.0 <= row.recall_at_k <= 1.0
        assert "coverage-based" in row.note  # metric definition is disclosed
    # Bigger budgets → coarser chunking → no more chunks than the baseline.
    assert merged_rows[0].n_chunks <= baseline.n_chunks
    assert merged_rows[1].n_chunks <= merged_rows[0].n_chunks


def test_chunk_sweep_is_deterministic(store: SqliteStore) -> None:
    first = run_chunk_sweep(store, build_golden_set(), sizes=[512], k=5)
    second = run_chunk_sweep(store, build_golden_set(), sizes=[512], k=5)
    assert first == second
