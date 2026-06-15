"""Typed domain models — the shared vocabulary for the whole system.

These Pydantic models are the contract that corpus generation, ground-truth
files, ingestion, and the eval harness all serialize through. Defining them once,
here, is what makes the Critic's verification mechanical rather than vibes
(Lessons-Learned #15: typed models at every boundary).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ConflictType(StrEnum):
    """The three seeded contradiction kinds (Project_plan Phase A)."""

    NUMERIC_MISMATCH = "numeric_mismatch"
    INCOMPATIBLE_CONSTRAINT = "incompatible_constraint"
    SUPERSEDED_REFERENCE = "superseded_reference"


class ScenarioTag(StrEnum):
    """Golden-question scenarios — one feature, many scenarios (principle #3)."""

    SUCCESS = "success"
    NO_RESULT = "no_result"
    MULTI_RESULT = "multi_result"
    CONTRADICTORY_RESULT = "contradictory_result"
    MISSING_DATA = "missing_data"
    PERMISSION_EDGE = "permission_edge"


class RequirementStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class EntityType(StrEnum):
    """What an extracted entity refers to."""

    REQUIREMENT = "requirement"
    PARAMETER = "parameter"


class Requirement(BaseModel):
    """A single requirement statement with its structural context."""

    model_config = {"frozen": True}

    id: str
    doc_id: str
    section: str
    title: str
    text: str
    category: str
    parameters: dict[str, str] = Field(default_factory=dict)
    refs: list[str] = Field(default_factory=list)
    status: RequirementStatus = RequirementStatus.ACTIVE
    superseded_by: str | None = None


class RequirementDocument(BaseModel):
    """One requirement document (renders to a single Markdown file)."""

    id: str
    title: str
    doc_type: str
    requirements: list[Requirement]


class Chunk(BaseModel):
    """A retrievable unit. One chunk per requirement keeps the requirement ID and its
    section hierarchy attached — structure-aware chunking for this corpus.
    """

    id: str
    doc_id: str
    requirement_id: str
    section_path: list[str]
    title: str
    text: str
    content_hash: str
    parameters: dict[str, str] = Field(default_factory=dict)
    status: RequirementStatus = RequirementStatus.ACTIVE


class Entity(BaseModel):
    """A requirement ID or a named parameter extracted from a requirement."""

    name: str
    entity_type: EntityType
    requirement_id: str
    doc_id: str
    value: str | None = None


class CrossRef(BaseModel):
    """A reference from one requirement to another. resolved is False when the target
    is not present in the corpus (a dangling reference, to be flagged).
    """

    from_req: str
    to_req: str
    resolved: bool


class Contradiction(BaseModel):
    """A ground-truth contradiction (or, when is_true_conflict is False, a near-miss).

    evidence_quote_a/b must be verbatim substrings of req_a/req_b text — the
    integrity tests enforce this, which is what keeps the ground truth honest.
    """

    id: str
    req_a: str
    req_b: str
    conflict_type: ConflictType
    evidence_quote_a: str
    evidence_quote_b: str
    rationale: str
    is_true_conflict: bool = True


class GoldenQuestion(BaseModel):
    """A graded Q&A item. expected_source_ids may be empty for no_result / missing_data."""

    id: str
    question: str
    expected_source_ids: list[str] = Field(default_factory=list)
    expected_facts: list[str] = Field(default_factory=list)
    scenario: ScenarioTag


class GroundTruth(BaseModel):
    """Top-level container serialized to the eval JSON files."""

    contradictions: list[Contradiction]
    questions: list[GoldenQuestion]
