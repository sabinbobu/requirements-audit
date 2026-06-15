"""Planner agent: routes a request to the Q&A or audit path and decomposes it.

Typed output (`Plan`) is the contract the orchestrator switches on. The agent is
constructed without a bound model; the model is supplied at run time
(`run_sync(..., model=...)`) on live runs, or injected via `agent.override(...)`
in tests. A keyword fast-path handles the unambiguous audit phrasing without an
LLM round-trip.
"""

from __future__ import annotations

from pydantic_ai import Agent

from requirements_audit.models import Plan, QueryRoute

INSTRUCTIONS = """\
You route a user's request about engineering requirement documents.

Choose route="audit" when the user wants to find, check for, or sweep for
contradictions, conflicts, inconsistencies, or mismatches *across* requirements
or documents. Choose route="qa" for any other question that seeks information or
a specific value from the requirements.

For a qa route, decompose a compound question into focused sub-questions in
`subqueries` (one entry per distinct information need); leave it empty for a
simple question. For an audit route, `subqueries` stays empty. Always give a
one-sentence `rationale`.
"""

_AUDIT_KEYWORDS = (
    "contradiction",
    "contradict",
    "conflict",
    "inconsistenc",
    "mismatch",
    "audit",
    "sweep",
)

planner_agent = Agent(
    output_type=Plan,
    instructions=INSTRUCTIONS,
    name="planner",
)


def quick_route(question: str) -> Plan | None:
    """LLM-free routing for unambiguous audit phrasing; None means ask the model."""
    lowered = question.lower()
    if any(word in lowered for word in _AUDIT_KEYWORDS):
        return Plan(
            route=QueryRoute.AUDIT,
            subqueries=[],
            rationale="Request explicitly asks about contradictions/conflicts.",
        )
    return None
