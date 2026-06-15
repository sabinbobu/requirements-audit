"""Entry point: ``python -m requirements_audit.corpus`` (also ``make corpus``)."""

from __future__ import annotations

from requirements_audit.corpus.generator import generate

if __name__ == "__main__":
    generate()
