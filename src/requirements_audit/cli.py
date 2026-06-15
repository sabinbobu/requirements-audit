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
) -> None:
    """Answer a requirement query with inline citations."""
    raise typer.Exit(_not_implemented("query"))


@app.command()
def audit() -> None:
    """Sweep the indexed corpus for cross-document contradictions."""
    raise typer.Exit(_not_implemented("audit"))


def _not_implemented(command: str) -> int:
    typer.secho(
        f"`{command}` is not implemented yet (Phase 1 scaffolding).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    return 1


if __name__ == "__main__":
    app()
