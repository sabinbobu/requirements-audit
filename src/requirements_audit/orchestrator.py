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

from collections.abc import Callable
from typing import Any

from pydantic_ai import UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from requirements_audit.agents import audit as audit_mod
from requirements_audit.agents.analyst import analyst_agent
from requirements_audit.agents.comparator import comparator_agent, comparator_prompt, to_candidate
from requirements_audit.agents.critic import critic_agent, critic_prompt
from requirements_audit.agents.planner import planner_agent, quick_route
from requirements_audit.config import Settings
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.llm.pricing import estimate_usd
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


def _usage_dict(usage: RunUsage) -> dict[str, int]:
    """The trace-facing view of a stage's token usage."""
    return {
        "requests": usage.requests,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


def _add_usage(detail: dict[str, Any], usage: RunUsage) -> None:
    """Accumulate a run's usage into a step's `detail["usage"]` (stages like the
    comparator make one agent run per candidate pair)."""
    bucket = detail.setdefault("usage", {"requests": 0, "input_tokens": 0, "output_tokens": 0})
    for key, value in _usage_dict(usage).items():
        bucket[key] += value


def _finish_with_usage(tracer: Tracer, settings: Settings, **outputs: Any) -> RunTrace:
    """Total the per-stage usage into run metadata with a cost estimate, so cost
    and latency are visible per request (Phase F) without a LangFuse round-trip."""
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    for step in tracer.trace.steps:
        for key, value in step.detail.get("usage", {}).items():
            totals[key] += value
    estimated = estimate_usd(
        settings.primary_model, totals["input_tokens"], totals["output_tokens"]
    )
    return tracer.finish(
        usage=totals,
        # Priced against the configured primary provider's model; a run that
        # fell back to the other provider is therefore an estimate, which is
        # exactly how it is labeled.
        estimated_usd=estimated,
        pricing_model=settings.primary_model,
        **outputs,
    )


def plan_request(
    question: str, settings: Settings, *, model: Model | None = None
) -> tuple[Plan, RunUsage | None]:
    """Route a request; uses the keyword fast-path before falling back to the
    Planner. Usage is None on the fast path (no LLM call happened)."""
    fast = quick_route(question)
    if fast is not None:
        return fast, None
    result = planner_agent.run_sync(question, model=model, usage_limits=usage_limits(settings))
    return result.output, result.usage


def answer_query(
    store: SqliteStore,
    question: str,
    settings: Settings,
    *,
    model: Model | None = None,
    tracer: Tracer | None = None,
) -> tuple[Answer, RunTrace]:
    """`tracer` is injectable so callers can observe stages live (the API streams
    them over SSE); when omitted a plain in-memory tracer is used."""
    deps = RetrievalDeps.from_store(store)
    if tracer is None:
        tracer = Tracer("query", settings, question=question)
    limits = usage_limits(settings)

    with tracer.step("plan") as detail:
        plan, plan_usage = plan_request(question, settings, model=model)
        detail["route"] = plan.route.value
        detail["subqueries"] = plan.subqueries
        if plan_usage is not None:  # None = keyword fast-path, no LLM call
            _add_usage(detail, plan_usage)

    with tracer.step("analyst") as detail:
        result = analyst_agent.run_sync(question, deps=deps, model=model, usage_limits=limits)
        answer = result.output
        detail["citations"] = [c.requirement_id for c in answer.citations]
        _add_usage(detail, result.usage)

    trace = _finish_with_usage(tracer, settings, citation_count=len(answer.citations))
    return answer, trace


def run_audit(
    store: SqliteStore,
    settings: Settings,
    *,
    model: Model | None = None,
    use_llm: bool | None = None,
    focus_doc: str | None = None,
    tracer: Tracer | None = None,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[AuditReport, RunTrace]:
    """Sweep for contradictions.

    `use_llm` defaults to whether a model is available: deterministic-only when no
    model (the gate-able path), full hybrid (comparator + Critic) when one is.

    `focus_doc`, when set, scopes candidate generation to pairs involving that
    document (compared against the rest of the corpus) — a fast, focused audit
    for a single document instead of the full corpus sweep.

    `tracer` is injectable so callers can observe stages live (the API streams
    them over SSE), mirroring `answer_query`. `progress_cb(done, total)` reports
    fine-grained progress through the comparator loop — the run's most
    expensive (LLM-bound) stage — for a determinate progress bar.
    """
    use_llm = (model is not None) if use_llm is None else use_llm
    if tracer is None:
        tracer = Tracer("audit", settings, use_llm=use_llm, focus_doc=focus_doc)
    limits = usage_limits(settings)

    focus_ids: set[str] | None = None
    if focus_doc is not None:
        focus_ids = {c.requirement_id for c in store.chunks_for_doc(focus_doc)}

    # Rule-based candidates (numeric mismatch, superseded reference) are
    # high-precision by construction — the keyless gate asserts they flag zero
    # near-misses — so they bypass the Critic and are auto-confirmed. Only the
    # LLM comparator's prose candidates need the Critic's false-positive filter;
    # running the Critic over the rule candidates too made it over-reject them
    # (dropping correct superseded findings below the deterministic recall floor).
    with tracer.step("deterministic_candidates") as detail:
        rule_candidates: list[CandidateContradiction] = list(
            audit_mod.deterministic_candidates(store)
        )
        if focus_ids is not None:
            rule_candidates = audit_mod.filter_candidates_by_doc(rule_candidates, focus_ids)
        detail["count"] = len(rule_candidates)

    llm_candidates: list[CandidateContradiction] = []
    if use_llm:
        exclude: set[tuple[str, str]] = {
            (c.req_a, c.req_b) if c.req_a <= c.req_b else (c.req_b, c.req_a)
            for c in rule_candidates
        }
        with tracer.step("llm_comparator") as detail:
            pairs = audit_mod.incompatible_candidate_pairs(
                store, max_pairs=settings.max_audit_pairs, exclude=exclude, focus_doc=focus_doc
            )
            total = len(pairs)
            for done, pair in enumerate(pairs, start=1):
                result = comparator_agent.run_sync(
                    comparator_prompt(pair), model=model, usage_limits=limits
                )
                _add_usage(detail, result.usage)
                if result.output.conflicts:
                    llm_candidates.append(to_candidate(pair, result.output))
                if progress_cb is not None:
                    progress_cb(done, total)
            detail["pairs_examined"] = len(pairs)
            detail["confirmed"] = len(llm_candidates)

    # Rule candidates go straight to findings; the Critic verifies only the
    # comparator's candidates.
    findings: list[Finding] = [Finding(candidate=c, verdict=_RULE_VERDICT) for c in rule_candidates]
    rejected = 0
    with tracer.step("critic") as detail:
        for candidate in llm_candidates:
            critic_result = critic_agent.run_sync(
                critic_prompt(candidate), model=model, usage_limits=limits
            )
            _add_usage(detail, critic_result.usage)
            if critic_result.output.is_conflict:
                findings.append(Finding(candidate=candidate, verdict=critic_result.output))
            else:
                rejected += 1
        detail["rule_bypassed"] = len(rule_candidates)
        detail["critic_reviewed"] = len(llm_candidates)
        detail["confirmed"] = len(findings)
        detail["rejected"] = rejected

    report = AuditReport(
        findings=findings,
        candidates_considered=len(rule_candidates) + len(llm_candidates),
        rejected_by_critic=rejected,
    )
    trace = _finish_with_usage(tracer, settings, findings=len(findings), rejected=rejected)
    return report, trace
