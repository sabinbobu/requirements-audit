"""Fixtures for the eval gate.

The deterministic fixtures (store, ground truth, thresholds) power the every-commit
gate. `live_model` skips the test when no API key is configured, so the Ragas /
judge / full-pipeline tests stay green-by-skipping in keyless CI and only run for
real in the nightly/live job.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from requirements_audit.config import Settings
from requirements_audit.eval.contradiction import GroundTruthPairs
from requirements_audit.eval.thresholds import Thresholds, load_thresholds
from requirements_audit.ingestion.pipeline import ingest_corpus
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Contradiction, GoldenQuestion

_ROOT = Path(__file__).resolve().parents[1]
_CORPUS = _ROOT / "corpus"
_EVALS = _ROOT / "evals"


@pytest.fixture
def store() -> Iterator[SqliteStore]:
    with SqliteStore(":memory:") as s:
        ingest_corpus(_CORPUS, s)
        yield s


@pytest.fixture(scope="session")
def golden_questions() -> list[GoldenQuestion]:
    raw = json.loads((_EVALS / "golden_set.json").read_text(encoding="utf-8"))
    return [GoldenQuestion(**q) for q in raw]


@pytest.fixture(scope="session")
def contradictions() -> list[Contradiction]:
    raw = json.loads((_EVALS / "contradictions.json").read_text(encoding="utf-8"))
    return [Contradiction(**c) for c in raw]


@pytest.fixture(scope="session")
def gt_pairs(contradictions: list[Contradiction]) -> GroundTruthPairs:
    return GroundTruthPairs.from_contradictions(contradictions)


@pytest.fixture(scope="session")
def thresholds() -> Thresholds:
    return load_thresholds()


@pytest.fixture(scope="session")
def live_model() -> object:
    """A real provider model, or skip the test if no API key is configured."""
    from requirements_audit.llm.provider import MissingCredentialsError, build_model

    try:
        return build_model(Settings())
    except MissingCredentialsError:
        pytest.skip("no API key configured; live eval runs in the nightly job")
