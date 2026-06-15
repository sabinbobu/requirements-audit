"""Comparator agent: judges whether a candidate pair is an incompatible constraint.

The `incompatible_constraint` class is prose/semantic and has no deterministic
rule signal (design doc). Candidate pairs are generated deterministically by
cross-document lexical neighbours (`agents.audit.incompatible_candidate_pairs`);
this agent decides, for one pair, whether the two requirements impose constraints
that cannot both be satisfied. Confirmed pairs become `CandidateContradiction`s
that still pass through the Critic.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai import Agent

from requirements_audit.agents.audit import ChunkPair
from requirements_audit.models import CandidateContradiction, ConflictType

INSTRUCTIONS = """\
You decide whether two engineering requirements impose *incompatible constraints* —
constraints that cannot both be satisfied by the same system at the same time
(e.g. "single controller, no redundancy" vs "dual redundant channels"; a response
budget shorter than a mandated minimum processing time; a sleep-current limit a
component cannot meet).

Only report a conflict for a genuine constraint incompatibility, not for two
requirements that merely share a topic. When conflicting, quote the deciding phrase
from each requirement verbatim.
"""


class ComparisonResult(BaseModel):
    conflicts: bool
    evidence_quote_a: str = ""
    evidence_quote_b: str = ""
    rationale: str = ""


comparator_agent = Agent(
    output_type=ComparisonResult,
    instructions=INSTRUCTIONS,
    name="comparator",
)


def comparator_prompt(pair: ChunkPair) -> str:
    return f"Requirement {pair.req_a}:\n{pair.text_a}\n\nRequirement {pair.req_b}:\n{pair.text_b}"


def to_candidate(pair: ChunkPair, result: ComparisonResult) -> CandidateContradiction:
    return CandidateContradiction(
        req_a=pair.req_a,
        req_b=pair.req_b,
        conflict_type=ConflictType.INCOMPATIBLE_CONSTRAINT,
        evidence_quote_a=result.evidence_quote_a or pair.text_a,
        evidence_quote_b=result.evidence_quote_b or pair.text_b,
        source="llm_comparator",
    )
