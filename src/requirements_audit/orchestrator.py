"""Orchestrator: typed entrypoints that wire the agents under budgets and tracing.

`answer_query` runs Planner → Analyst for the Q&A path; `run_audit` runs the
candidate generators (deterministic, plus the LLM comparator when a model is
available) → Critic for the audit path. Both record every stage via `Tracer` and
cap each agent run with `UsageLimits` derived from `Settings` (loop/token caps).

Model handling: the `model` is injected, not hard-wired. Live runs pass the model
the CLI builds from `Settings`; tests pass a `TestModel`/`FunctionModel`, so the
whole graph runs deterministically with no keys. The deterministic audit path
(`use_llm=False`) never invokes an agent, so it runs with `model=None`.
"""

from __future__ import annotations

from pydantic_ai import UsageLimits
from pydantic_ai.models import Model

from requirements_audit.agents import audit as audit_mod
from requirements_audit.agents.analyst import analyst_agent
from requirements_audit.agents.comparator import comparator_agent, comparator_prompt, to_candidate
from requirements_audit.agents.critic import critic_agent, critic_prompt
from requirements_audit.agents.planner import planner_agent, quick_route
from requirements_audit.config import Settings
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import (
    Answer,
    AuditReport,
    CandidateContradiction,
    CriticVerdict,
    Finding,
    Plan,
)
from requirements_audit.tools.retriever import RetrievalDeps
from requirements_audit.tracing import RunTrace, Tracer

# Verdict applied to a deterministic-rule candidate when no LLM Critic runs:
# the numeric/superseded rules are high-precision by construction.
_RULE_VERDICT = CriticVerdict(
    is_conflict=True, confidence=1.0, rationale="Deterministic rule match (not LLM-verified)."
)


def usage_limits(settings: Settings) -> UsageLimits:
    """Per-run loop/token caps. (USD cap is tracked separately in Phase E.)"""
    return UsageLimits(
        request_limit=settings.max_agent_steps,
        total_tokens_limit=settings.max_tokens_per_run,
    )


def plan_request(question: str, settings: Settings, *, model: Model | None = None) -> Plan:
    """Route a request; uses the keyword fast-path before falling back to the Planner."""
    fast = quick_route(question)
    if fast is not None:
        return fast
    return planner_agent.run_sync(question, model=model, usage_limits=usage_limits(settings)).output


def answer_query(
    store: SqliteStore,
    question: str,
    settings: Settings,
    *,
    model: Model | None = None,
) -> tuple[Answer, RunTrace]:
    deps = RetrievalDeps.from_store(store)
    tracer = Tracer("query", settings, question=question)
    limits = usage_limits(settings)

    with tracer.step("plan") as detail:
        plan = plan_request(question, settings, model=model)
        detail["route"] = plan.route.value
        detail["subqueries"] = plan.subqueries

    with tracer.step("analyst") as detail:
        result = analyst_agent.run_sync(question, deps=deps, model=model, usage_limits=limits)
        answer = result.output
        detail["citations"] = [c.requirement_id for c in answer.citations]

    trace = tracer.finish(citation_count=len(answer.citations))
    return answer, trace


def run_audit(
    store: SqliteStore,
    settings: Settings,
    *,
    model: Model | None = None,
    use_llm: bool | None = None,
) -> tuple[AuditReport, RunTrace]:
    """Sweep for contradictions.

    `use_llm` defaults to whether a model is available: deterministic-only when no
    model (the gate-able path), full hybrid (comparator + Critic) when one is.
    """
    use_llm = (model is not None) if use_llm is None else use_llm
    tracer = Tracer("audit", settings, use_llm=use_llm)
    limits = usage_limits(settings)

    with tracer.step("deterministic_candidates") as detail:
        candidates: list[CandidateContradiction] = list(audit_mod.deterministic_candidates(store))
        detail["count"] = len(candidates)

    if use_llm:
        exclude: set[tuple[str, str]] = {
            (c.req_a, c.req_b) if c.req_a <= c.req_b else (c.req_b, c.req_a) for c in candidates
        }
        with tracer.step("llm_comparator") as detail:
            pairs = audit_mod.incompatible_candidate_pairs(
                store, max_pairs=settings.max_audit_pairs, exclude=exclude
            )
            confirmed = 0
            for pair in pairs:
                result = comparator_agent.run_sync(
                    comparator_prompt(pair), model=model, usage_limits=limits
                )
                if result.output.conflicts:
                    candidates.append(to_candidate(pair, result.output))
                    confirmed += 1
            detail["pairs_examined"] = len(pairs)
            detail["confirmed"] = confirmed

    findings: list[Finding] = []
    rejected = 0
    with tracer.step("critic") as detail:
        for candidate in candidates:
            if use_llm:
                verdict = critic_agent.run_sync(
                    critic_prompt(candidate), model=model, usage_limits=limits
                ).output
            else:
                verdict = _RULE_VERDICT
            if verdict.is_conflict:
                findings.append(Finding(candidate=candidate, verdict=verdict))
            else:
                rejected += 1
        detail["confirmed"] = len(findings)
        detail["rejected"] = rejected

    report = AuditReport(
        findings=findings,
        candidates_considered=len(candidates),
        rejected_by_critic=rejected,
    )
    trace = tracer.finish(findings=len(findings), rejected=rejected)
    return report, trace
