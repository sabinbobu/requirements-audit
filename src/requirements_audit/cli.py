"""Command-line interface for requirements-audit.

The commands below mirror the Quickstart in the README. They are intentional
stubs for now — Phase 1 establishes the entry point and the contract; the
implementations land in later phases (ingestion, retrieval, agents, eval).
"""

from __future__ import annotations

from pathlib import Path

import typer

from requirements_audit import __version__

app = typer.Typer(
    name="requirements-audit",
    help="Multi-agent contradiction detection over engineering requirement documents.",
    no_args_is_help=True,
    add_completion=False,
)


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
        answer, _trace = answer_query(store, question, settings, model=model)

    typer.echo(answer.text)
    if answer.citations:
        typer.echo("\nSources:")
        for c in answer.citations:
            typer.echo(f"  [{c.doc_id} · {c.requirement_id}] {c.quote}")
    else:
        typer.secho("\n(no supporting sources in the corpus)", fg=typer.colors.YELLOW)


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
        report, _trace = run_audit(store, settings, model=model, use_llm=use_llm)

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


if __name__ == "__main__":
    app()
