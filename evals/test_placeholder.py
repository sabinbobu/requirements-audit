"""Placeholder for the evaluation gate.

The real harness (golden set, seeded contradictions, Ragas, calibrated
LLM-judge) lands in Phase 3. This keeps `make eval` and the CI eval stage
wired up — and green — from day one.
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_eval_harness_placeholder() -> None:
    pytest.skip("eval harness not implemented yet (Phase 3)")
