"""Phase E chunk-size sweep.

The production chunker is one-chunk-per-requirement (requirements are atomic, and
citations need requirement IDs). The sweep asks whether *coarser* chunks — several
consecutive requirements merged up to a token budget — would retrieve better. Merged
chunks never cross a document section (structure-aware, like the real chunker).

Scoring against requirement-level ground truth needs restated metrics, disclosed here
and in each result's `note`:

- recall@k   — fraction of a question's expected requirement IDs covered by the
               union of the top-k retrieved chunks. Comparable across chunk sizes.
- precision@k — fraction of the top-k retrieved chunks containing at least one
               expected requirement. NOT comparable to the per-requirement
               benchmark's precision (a big chunk is "relevant" if any of its
               requirements is), which is why the sweep reports the
               per-requirement baseline scored the same way.

Deterministic (BM25 only), so the sweep runs with no keys and no services.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from requirements_audit.eval.benchmark import BenchmarkStatus
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk, GoldenQuestion
from requirements_audit.retrieval.lexical import LexicalIndex, tokenize

# Sentinel size for the unmerged one-chunk-per-requirement baseline row.
PER_REQUIREMENT = 0


class MergedChunking(BaseModel):
    """A corpus re-chunked at a token budget: synthetic chunks + coverage map."""

    chunks: list[Chunk]
    # merged chunk id -> the requirement IDs whose text it contains
    covered: dict[str, list[str]]


class ChunkSweepResult(BaseModel):
    chunk_size: int  # token budget; PER_REQUIREMENT (0) = unmerged baseline
    status: BenchmarkStatus
    k: int
    n_chunks: int
    n_questions: int
    precision_at_k: float
    recall_at_k: float
    note: str = ""


class ChunkSweepReport(BaseModel):
    sweep: list[ChunkSweepResult]


def _merged_text(members: list[Chunk]) -> str:
    """Concatenate member requirements the way the dense arm renders a chunk:
    title, body, and parameter pairs — so BM25 sees the same information."""
    parts: list[str] = []
    for c in members:
        params = " ".join(f"{k} {v}" for k, v in c.parameters.items())
        parts.append(f"{c.title}\n{c.text}\n{params}".rstrip())
    return "\n\n".join(parts)


def merge_chunks(chunks: list[Chunk], max_tokens: int) -> MergedChunking:
    """Greedily merge consecutive requirement chunks up to `max_tokens` tokens.

    Groups never cross a (doc, section) boundary. A single requirement larger
    than the budget still becomes its own chunk — requirements are atomic and
    splitting them would detach text from its requirement ID.
    """
    merged: list[Chunk] = []
    covered: dict[str, list[str]] = {}

    group: list[Chunk] = []
    group_tokens = 0

    def _flush() -> None:
        nonlocal group, group_tokens
        if not group:
            return
        first = group[0]
        chunk_id = f"merged-{len(merged):04d}"
        text = _merged_text(group)
        merged.append(
            Chunk(
                id=chunk_id,
                doc_id=first.doc_id,
                # A merged chunk spans requirements; the first member's ID keeps
                # the field meaningful for ranking tie-breaks. Coverage lives in
                # the `covered` map, which is what the sweep scores against.
                requirement_id=first.requirement_id,
                section_path=first.section_path,
                title=f"{first.doc_id} · {' / '.join(first.section_path)}",
                text=text,
                content_hash=first.content_hash,
                parameters={},
            )
        )
        covered[chunk_id] = [c.requirement_id for c in group]
        group, group_tokens = [], 0

    previous_key: tuple[str, str] | None = None
    for chunk in chunks:
        key = (chunk.doc_id, chunk.section_path[-1] if chunk.section_path else "")
        n_tokens = len(tokenize(f"{chunk.title}\n{chunk.text}"))
        # Start a new group on section change or when the budget would overflow.
        if group and (key != previous_key or group_tokens + n_tokens > max_tokens):
            _flush()
        group.append(chunk)
        group_tokens += n_tokens
        previous_key = key
    _flush()

    return MergedChunking(chunks=merged, covered=covered)


def _score_chunking(
    chunking: MergedChunking, questions: list[GoldenQuestion], k: int
) -> tuple[float, float, int]:
    """(precision@k, recall@k, n_questions) with the coverage-based definitions
    from the module docstring."""
    index = LexicalIndex(chunking.chunks)
    scored = [q for q in questions if q.expected_source_ids]
    if not scored:
        return 0.0, 0.0, 0

    p_total = r_total = 0.0
    for q in scored:
        hits = index.search(q.question, k)
        expected = set(q.expected_source_ids)
        covered_per_hit = [set(chunking.covered[h.chunk.id]) for h in hits]
        relevant_hits = sum(1 for ids in covered_per_hit if ids & expected)
        covered_union = set().union(*covered_per_hit) if covered_per_hit else set()
        p_total += relevant_hits / k
        r_total += len(expected & covered_union) / len(expected)

    n = len(scored)
    return p_total / n, r_total / n, n


def run_chunk_sweep(
    store: SqliteStore,
    questions: list[GoldenQuestion],
    *,
    sizes: list[int] | None = None,
    k: int = 5,
) -> ChunkSweepReport:
    """Score the per-requirement baseline plus each merged token budget.

    All rows use the same coverage-based metrics so they are comparable with
    each other (and deliberately NOT with the strategy benchmark's precision).
    """
    budgets = sizes or [256, 512, 1024]
    chunks = store.all_chunks()
    results: list[ChunkSweepResult] = []

    # Baseline: the production chunking, scored with identical coverage metrics.
    baseline = MergedChunking(chunks=chunks, covered={c.id: [c.requirement_id] for c in chunks})
    for size, chunking in [
        (PER_REQUIREMENT, baseline),
        *[(s, merge_chunks(chunks, s)) for s in budgets],
    ]:
        precision, recall, n_questions = _score_chunking(chunking, questions, k)
        label = "per-requirement baseline" if size == PER_REQUIREMENT else f"{size}-token merge"
        results.append(
            ChunkSweepResult(
                chunk_size=size,
                status=BenchmarkStatus.MEASURED,
                k=k,
                n_chunks=len(chunking.chunks),
                n_questions=n_questions,
                precision_at_k=precision,
                recall_at_k=recall,
                note=(
                    f"BM25 over {label}; coverage-based P/R "
                    "(chunk counts as relevant if it contains any expected requirement)."
                ),
            )
        )

    return ChunkSweepReport(sweep=results)


def write_sweep_report(report: ChunkSweepReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
