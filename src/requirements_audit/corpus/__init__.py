"""Synthetic corpus generation and ground-truth authoring (Project_plan Phase A).

Deterministic by construction: `python -m requirements_audit.corpus` regenerates a
byte-identical corpus plus the two eval ground-truth files. The seeded
contradictions live in `spec.py`; `generator.py` lays them into documents and
emits the artifacts.
"""

from __future__ import annotations
