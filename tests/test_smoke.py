"""Smoke tests — prove the package imports and the CLI wires up.

These exist so CI has a green target from commit one and so the eval gate has a
place to grow into. Replace/expand as real modules land.
"""

from __future__ import annotations

from typer.testing import CliRunner

from requirements_audit import __version__
from requirements_audit.cli import app

runner = CliRunner()


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_cli_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "requirements-audit" in result.stdout


def test_cli_help_lists_core_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("ingest", "query", "audit"):
        assert command in result.stdout
