"""Critic agent: verifies a candidate contradiction against its quoted sources.

The Critic is the false-positive filter that the "before vs after Critic" precision
metric measures. It receives a candidate and the two requirement texts, and judges
whether they genuinely conflict — rejecting near-misses (e.g. mode-qualified values,
a value that sits inside a stated range, a reference to an *active* requirement).
Typed `CriticVerdict` output with a confidence score.
"""

from __future__ import annotations

from pydantic_ai import Agent

from requirements_audit.models import CandidateContradiction, CriticVerdict

INSTRUCTIONS = """\
You verify whether two engineering requirements genuinely contradict each other.

You are given a proposed conflict type and the verbatim text of both requirements.
Confirm a conflict only if the two statements cannot both hold for the same system
under the same conditions. Reject false positives, including:
  - values that differ but are qualified to different modes/conditions,
  - a value that falls within a range stated by the other requirement,
  - a reference to a requirement that is current (not superseded),
  - identical values stated in two places.

Return is_conflict, a confidence in [0,1], and a one-sentence rationale that quotes
the deciding phrase from each requirement.
"""

critic_agent = Agent(
    output_type=CriticVerdict,
    instructions=INSTRUCTIONS,
    name="critic",
)


def critic_prompt(candidate: CandidateContradiction) -> str:
    return (
        f"Proposed conflict type: {candidate.conflict_type.value}\n\n"
        f"Requirement {candidate.req_a}:\n{candidate.evidence_quote_a}\n\n"
        f"Requirement {candidate.req_b}:\n{candidate.evidence_quote_b}"
    )
