"""L1 integrity tests for the synthetic corpus and ground truth.

These are cheap, deterministic, and unmarked, so they run on *every* commit
(CI's ``pytest -m "not eval"`` stage). They are the guardrail that stops a future
corpus edit from silently breaking the eval ruler — the property the build agent
is told to protect ("ground truth by construction").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from requirements_audit.corpus import generator
from requirements_audit.models import (
    Contradiction,
    GoldenQuestion,
    Requirement,
    RequirementStatus,
    ScenarioTag,
)

_ID_RE = re.compile(r"^[A-Z]+-REQ-\d{4}$")
_SOURCED_SCENARIOS = {
    ScenarioTag.SUCCESS,
    ScenarioTag.MULTI_RESULT,
    ScenarioTag.CONTRADICTORY_RESULT,
}
_EMPTY_SCENARIOS = {
    ScenarioTag.NO_RESULT,
    ScenarioTag.MISSING_DATA,
    ScenarioTag.PERMISSION_EDGE,
}

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def requirements() -> dict[str, Requirement]:
    reqs: dict[str, Requirement] = {}
    for doc in generator.build_documents():
        for req in doc.requirements:
            reqs[req.id] = req
    return reqs


@pytest.fixture(scope="module")
def contradictions() -> list[Contradiction]:
    return generator.build_contradictions()


@pytest.fixture(scope="module")
def questions() -> list[GoldenQuestion]:
    return generator.build_golden_set()


# ─── counts ──────────────────────────────────────────────────────────────────
def test_document_count() -> None:
    assert len(generator.build_documents()) == 8


def test_requirement_count_in_range(requirements: dict[str, Requirement]) -> None:
    assert 150 <= len(requirements) <= 300


def test_exactly_15_true_and_5_near_miss(contradictions: list[Contradiction]) -> None:
    true = [c for c in contradictions if c.is_true_conflict]
    near = [c for c in contradictions if not c.is_true_conflict]
    assert len(true) == 15
    assert len(near) == 5


def test_golden_set_has_50_questions(questions: list[GoldenQuestion]) -> None:
    assert len(questions) == 50


def test_all_six_scenarios_present(questions: list[GoldenQuestion]) -> None:
    assert {q.scenario for q in questions} == set(ScenarioTag)


# ─── requirement well-formedness ──────────────────────────────────────────────
def test_requirement_ids_unique_and_well_formed(requirements: dict[str, Requirement]) -> None:
    for rid, req in requirements.items():
        assert _ID_RE.match(rid), f"bad id format: {rid}"
        assert rid.startswith(req.doc_id + "-"), f"id/doc_id mismatch: {rid} vs {req.doc_id}"


def test_no_empty_requirement_bodies(requirements: dict[str, Requirement]) -> None:
    for req in requirements.values():
        assert req.text.strip(), f"empty body: {req.id}"
        assert req.title.strip(), f"empty title: {req.id}"


def test_all_refs_resolve(requirements: dict[str, Requirement]) -> None:
    for req in requirements.values():
        for ref in req.refs:
            assert ref in requirements, f"{req.id} references unknown {ref}"


def test_superseded_requirements_point_to_existing_replacement(
    requirements: dict[str, Requirement],
) -> None:
    for req in requirements.values():
        if req.status is RequirementStatus.SUPERSEDED:
            assert req.superseded_by, f"{req.id} is superseded but names no replacement"
            assert req.superseded_by in requirements, (
                f"{req.id} superseded_by unknown {req.superseded_by}"
            )


# ─── contradiction ground-truth integrity ────────────────────────────────────
def test_contradiction_endpoints_exist(
    contradictions: list[Contradiction], requirements: dict[str, Requirement]
) -> None:
    for c in contradictions:
        assert c.req_a in requirements, f"{c.id} req_a missing: {c.req_a}"
        assert c.req_b in requirements, f"{c.id} req_b missing: {c.req_b}"


def test_evidence_quotes_are_verbatim_substrings(
    contradictions: list[Contradiction], requirements: dict[str, Requirement]
) -> None:
    for c in contradictions:
        text_a = requirements[c.req_a].text
        text_b = requirements[c.req_b].text
        assert c.evidence_quote_a in text_a, f"{c.id}: quote_a not in {c.req_a}"
        assert c.evidence_quote_b in text_b, f"{c.id}: quote_b not in {c.req_b}"


def test_true_contradictions_span_documents(contradictions: list[Contradiction]) -> None:
    # A cross-document contradiction is the whole point; both endpoints should
    # not live in the same document.
    for c in contradictions:
        if c.is_true_conflict:
            assert c.req_a.split("-")[0] != c.req_b.split("-")[0], f"{c.id} is intra-document"


# ─── golden-set integrity ─────────────────────────────────────────────────────
def test_golden_ids_unique(questions: list[GoldenQuestion]) -> None:
    ids = [q.id for q in questions]
    assert len(ids) == len(set(ids))
    assert all(q.id for q in questions), "every question must have an id"


def test_sourced_questions_resolve(
    questions: list[GoldenQuestion], requirements: dict[str, Requirement]
) -> None:
    for q in questions:
        if q.scenario in _SOURCED_SCENARIOS:
            assert q.expected_source_ids, f"{q.id} ({q.scenario}) has no expected sources"
            for sid in q.expected_source_ids:
                assert sid in requirements, f"{q.id} expects unknown source {sid}"


def test_empty_scenarios_have_no_sources(questions: list[GoldenQuestion]) -> None:
    for q in questions:
        if q.scenario in _EMPTY_SCENARIOS:
            assert not q.expected_source_ids, f"{q.id} ({q.scenario}) should have no sources"


# ─── committed artifacts are up to date ───────────────────────────────────────
def test_committed_ground_truth_matches_generator(
    contradictions: list[Contradiction], questions: list[GoldenQuestion]
) -> None:
    """Guards that someone regenerated (`make corpus`) after editing the spec."""
    on_disk_c = json.loads((_ROOT / "evals" / "contradictions.json").read_text(encoding="utf-8"))
    on_disk_q = json.loads((_ROOT / "evals" / "golden_set.json").read_text(encoding="utf-8"))
    assert on_disk_c == [c.model_dump(mode="json") for c in contradictions]
    assert on_disk_q == [q.model_dump(mode="json") for q in questions]


def test_committed_corpus_files_match_generator() -> None:
    """Guards the generator-owned corpus files against silent edits — checked
    by filename, so user-added documents in corpus/ are deliberately ignored
    (dropping your own specs into corpus/ is the supported workflow)."""
    for doc in generator.build_documents():
        on_disk = (_ROOT / "corpus" / f"{doc.id}.md").read_text(encoding="utf-8")
        assert on_disk == generator.render_markdown(doc), (
            f"corpus/{doc.id}.md drifted from the generator — run `make corpus`"
        )
