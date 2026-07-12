"""Command-line interface for requirements-audit."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from requirements_audit import __version__

if TYPE_CHECKING:
    from requirements_audit.tracing import RunTrace

app = typer.Typer(
    name="requirements-audit",
    help="Multi-agent contradiction detection over engineering requirement documents.",
    no_args_is_help=True,
    add_completion=False,
)


def _run_stats(trace: "RunTrace") -> str:  # noqa: UP037 - runtime import stays lazy
    """One ops line per run: latency, tokens, and the estimated cost.

    Written to stderr so piping stdout (the answer / findings) stays clean.
    """
    usage = trace.metadata.get("usage") or {}
    tokens = f"{usage.get('input_tokens', 0)} in / {usage.get('output_tokens', 0)} out"
    estimated = trace.metadata.get("estimated_usd")
    cost = (
        f"~${estimated:.4f} (est., {trace.metadata.get('pricing_model')})"
        if estimated is not None and usage.get("requests", 0) > 0
        else "$0 (no LLM calls)"
    )
    return f"[{trace.total_latency_ms:.0f} ms · {tokens} tokens · {cost}]"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"requirements-audit {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


@app.command()
def ingest(
    corpus: Path = typer.Argument(..., help="Directory of documents to index."),
    db: Path = typer.Option(Path("data/requirements.sqlite"), "--db", help="SQLite store path."),
) -> None:
    """Parse, chunk, and extract a corpus into the SQLite store (idempotent)."""
    from requirements_audit.ingestion.pipeline import ingest_corpus
    from requirements_audit.ingestion.store import SqliteStore

    if not corpus.is_dir():
        typer.secho(f"Corpus directory not found: {corpus}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    with SqliteStore(db) as store:
        report = ingest_corpus(corpus, store)

    typer.echo(
        f"Documents: {len(report.new_docs)} new, {len(report.updated_docs)} updated, "
        f"{len(report.unchanged_docs)} unchanged."
    )
    typer.echo(
        f"Store now holds {report.chunks} chunks, {report.entities} entities, "
        f"{report.refs} references ({report.unresolved_refs} unresolved)."
    )


@app.command()
def query(
    question: str = typer.Argument(..., help="A natural-language requirement query."),
    db: Path = typer.Option(Path("data/requirements.sqlite"), "--db", help="SQLite store path."),
) -> None:
    """Answer a requirement query with inline citations."""
    from requirements_audit.config import Settings
    from requirements_audit.ingestion.store import SqliteStore
    from requirements_audit.llm.provider import MissingCredentialsError, build_model
    from requirements_audit.orchestrator import answer_query

    settings = Settings()
    try:
        model = build_model(settings)
    except MissingCredentialsError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    with SqliteStore(db) as store:
        answer, trace = answer_query(store, question, settings, model=model)

    typer.echo(answer.text)
    if answer.citations:
        typer.echo("\nSources:")
        for c in answer.citations:
            typer.echo(f"  [{c.doc_id} · {c.requirement_id}] {c.quote}")
    else:
        typer.secho("\n(no supporting sources in the corpus)", fg=typer.colors.YELLOW)
    typer.secho(_run_stats(trace), fg=typer.colors.BLUE, err=True)


@app.command()
def audit(
    db: Path = typer.Option(Path("data/requirements.sqlite"), "--db", help="SQLite store path."),
    llm: bool | None = typer.Option(
        None,
        "--llm/--no-llm",
        help="Force the LLM comparator+Critic on/off. Default: on when API keys are set.",
    ),
) -> None:
    """Sweep the indexed corpus for cross-document contradictions."""
    from requirements_audit.config import Settings
    from requirements_audit.ingestion.store import SqliteStore
    from requirements_audit.llm.provider import MissingCredentialsError, build_model
    from requirements_audit.orchestrator import run_audit

    settings = Settings()
    use_llm = llm if llm is not None else None
    model = None
    if use_llm is not False:
        try:
            model = build_model(settings)
        except MissingCredentialsError:
            if use_llm:  # explicitly requested but unavailable
                typer.secho(
                    "LLM requested but no API key configured; run with --no-llm for the "
                    "deterministic classes only.",
                    fg=typer.colors.RED,
                    err=True,
                )
                raise typer.Exit(1) from None
            typer.secho(
                "No API key: auditing the deterministic classes only "
                "(numeric mismatch, superseded reference).",
                fg=typer.colors.YELLOW,
                err=True,
            )

    with SqliteStore(db) as store:
        report, trace = run_audit(store, settings, model=model, use_llm=use_llm)

    if not report.findings:
        typer.echo("No contradictions found.")
    for finding in report.findings:
        c = finding.candidate
        v = finding.verdict
        typer.echo(
            f"[{c.conflict_type.value}] {c.req_a} ↔ {c.req_b} "
            f"(confidence {v.confidence:.2f}, {finding.human_status.value})"
        )
        typer.echo(f"    A: {c.evidence_quote_a}")
        typer.echo(f"    B: {c.evidence_quote_b}")
    typer.echo(
        f"\n{len(report.findings)} finding(s) from {report.candidates_considered} candidate(s); "
        f"{report.rejected_by_critic} rejected by the Critic."
    )
    typer.secho(_run_stats(trace), fg=typer.colors.BLUE, err=True)


@app.command()
def benchmark(
    db: Path = typer.Option(Path("data/requirements.sqlite"), "--db", help="SQLite store path."),
    golden_set: Path = typer.Option(
        Path("evals/golden_set.json"), "--golden-set", help="Golden questions JSON path."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON report to a file."),
    k: int = typer.Option(5, "--k", min=1, help="Top-k retrieval cutoff."),
    strategies: list[str] | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="Retrieval strategy to include; repeatable. Defaults to lexical.",
    ),
    embedder: str = typer.Option(
        "auto",
        "--embedder",
        help="Embedding backend for dense/hybrid: auto, hash, or openai. "
        "auto = openai when OPENAI_API_KEY is set, else the deterministic hash embedder.",
    ),
) -> None:
    """Run Phase E retrieval benchmarks and emit a JSON report."""
    from requirements_audit.config import Settings
    from requirements_audit.eval.benchmark import (
        RetrievalStrategy,
        load_golden_questions,
        run_retrieval_benchmark,
        write_report,
    )
    from requirements_audit.ingestion.store import SqliteStore
    from requirements_audit.llm.provider import MissingCredentialsError
    from requirements_audit.retrieval.embedding import EmbedderChoice, build_embedder

    try:
        selected = [RetrievalStrategy(s) for s in strategies] if strategies else None
    except ValueError as exc:
        valid = ", ".join(s.value for s in RetrievalStrategy)
        typer.secho(
            f"Unknown strategy: {exc}. Valid strategies: {valid}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(1) from exc

    # Only resolve an embedder when a selected strategy actually needs one, so
    # the default lexical run never consults keys or builds a vector index.
    needs_embedder = any(s is not RetrievalStrategy.LEXICAL for s in (selected or []))
    resolved_embedder = None
    if needs_embedder:
        try:
            resolved_embedder = build_embedder(Settings(), EmbedderChoice(embedder))
        except ValueError as exc:
            valid = ", ".join(c.value for c in EmbedderChoice)
            typer.secho(
                f"Unknown embedder: {embedder}. Valid embedders: {valid}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1) from exc
        except MissingCredentialsError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    questions = load_golden_questions(golden_set)
    with SqliteStore(db) as store:
        if store.chunk_count() == 0:
            typer.secho(
                f"No chunks found in {db}; run `requirements-audit ingest corpus/ --db {db}` first.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        report = run_retrieval_benchmark(
            store, questions, strategies=selected, k=k, embedder=resolved_embedder
        )

    if output is not None:
        write_report(report, output)
        typer.echo(f"Wrote benchmark report to {output}")
    else:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


@app.command("chunk-sweep")
def chunk_sweep(
    db: Path = typer.Option(Path("data/requirements.sqlite"), "--db", help="SQLite store path."),
    golden_set: Path = typer.Option(
        Path("evals/golden_set.json"), "--golden-set", help="Golden questions JSON path."
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write JSON report to a file."),
    k: int = typer.Option(5, "--k", min=1, help="Top-k retrieval cutoff."),
    sizes: list[int] | None = typer.Option(
        None,
        "--size",
        "-s",
        help="Merge token budget to sweep; repeatable. Defaults to 256, 512, 1024.",
    ),
) -> None:
    """Sweep chunk sizes (merged-requirement budgets) against the per-requirement baseline."""
    from requirements_audit.eval.benchmark import load_golden_questions
    from requirements_audit.eval.sweep import run_chunk_sweep, write_sweep_report
    from requirements_audit.ingestion.store import SqliteStore

    questions = load_golden_questions(golden_set)
    with SqliteStore(db) as store:
        if store.chunk_count() == 0:
            typer.secho(
                f"No chunks found in {db}; run `requirements-audit ingest corpus/ --db {db}` first.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        report = run_chunk_sweep(store, questions, sizes=sizes, k=k)

    if output is not None:
        write_sweep_report(report, output)
        typer.echo(f"Wrote chunk-sweep report to {output}")
    else:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    app()
