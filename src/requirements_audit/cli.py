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
) -> None:
    """Parse, chunk, and index a corpus into Qdrant + the SQLite entity store."""
    raise typer.Exit(_not_implemented("ingest"))


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
