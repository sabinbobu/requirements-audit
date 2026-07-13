"""Agent + orchestrator wiring tests, driven by PydanticAI FunctionModels.

No API keys, no network: a `FunctionModel` stands in for each LLM so the whole
graph — Planner routing, Analyst tool-calls + citations, the Critic filter, and
the audit pipeline end to end — runs deterministically in CI. The audit "oracle"
test proves that *given correct judgements* the pipeline recovers all 15 seeded
conflicts and rejects the near-misses; the LLM's real judgement quality is a
separate, live/nightly measurement.
"""

from __future__ import annotations

import re

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from requirements_audit.agents.analyst import analyst_agent
from requirements_audit.agents.audit import deterministic_candidates
from requirements_audit.agents.comparator import ComparisonResult, comparator_prompt, to_candidate
from requirements_audit.agents.planner import planner_agent, quick_route
from requirements_audit.config import Settings
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import QueryRoute
from requirements_audit.orchestrator import answer_query, run_audit, usage_limits
from requirements_audit.tools.retriever import RetrievalDeps


def _prompt_text(messages: list[ModelMessage]) -> str:
    return "".join(
        getattr(part, "content", "") or ""
        for message in messages
        for part in message.parts
        if getattr(part, "part_kind", "") in {"user-prompt", "system-prompt"}
    )


def _output_props(info: AgentInfo) -> set[str]:
    return set(info.output_tools[0].parameters_json_schema.get("properties", {}))


def _final(info: AgentInfo, args: dict[str, object]) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])


# ─── Planner ─────────────────────────────────────────────────────────────────
def test_quick_route_detects_audit_intent() -> None:
    audit = quick_route("Find contradictions across the documents")
    assert audit is not None and audit.route is QueryRoute.AUDIT
    conflicting = quick_route("are there any conflicting requirements?")
    assert conflicting is not None and conflicting.route is QueryRoute.AUDIT
    assert quick_route("What is the watchdog timeout?") is None


def test_planner_agent_returns_typed_plan() -> None:
    def planner_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return _final(info, {"route": "qa", "subqueries": ["a", "b"], "rationale": "r"})

    result = planner_agent.run_sync(
        "Tell me about timing and memory", model=FunctionModel(planner_fn)
    )
    assert result.output.route is QueryRoute.QA
    assert result.output.subqueries == ["a", "b"]


# ─── Analyst (Q&A) end to end via the orchestrator ───────────────────────────
def _qa_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if "route" in _output_props(info):  # planner step
        return _final(info, {"route": "qa", "subqueries": [], "rationale": "info request"})
    # analyst step: search first, then answer once a tool has returned.
    tool_returned = any(
        isinstance(part, ToolReturnPart) for message in messages for part in message.parts
    )
    if not tool_returned:
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name="hybrid_search", args={"query": "watchdog timeout", "k": 3})
            ]
        )
    return _final(
        info,
        {
            "question": "What is the watchdog timeout?",
            "text": "The watchdog supervision timeout is 100 ms.",
            "citations": [{"doc_id": "SYS", "requirement_id": "SYS-REQ-0101", "quote": "100 ms"}],
        },
    )


def test_answer_query_routes_and_cites(store: SqliteStore) -> None:
    settings = Settings()
    answer, trace = answer_query(
        store, "What is the watchdog timeout?", settings, model=FunctionModel(_qa_fn)
    )
    assert answer.citations and answer.citations[0].requirement_id == "SYS-REQ-0101"
    assert [s.name for s in trace.steps] == ["plan", "analyst"]
    plan_step = next(s for s in trace.steps if s.name == "plan")
    assert plan_step.detail["route"] == "qa"


def test_analyst_calls_a_retrieval_tool(store: SqliteStore) -> None:
    deps = RetrievalDeps.from_store(store)

    def analyst_only(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tool_returned = any(
            isinstance(part, ToolReturnPart) for message in messages for part in message.parts
        )
        if not tool_returned:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="get_section", args={"doc_id": "SYS", "section": "Timing"}
                    )
                ]
            )
        return _final(info, {"question": "q", "text": "answer", "citations": []})

    result = analyst_agent.run_sync("anything", deps=deps, model=FunctionModel(analyst_only))
    called = {
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    assert "get_section" in called


# ─── Comparator helper ───────────────────────────────────────────────────────
def test_to_candidate_falls_back_to_full_text() -> None:
    from requirements_audit.agents.audit import ChunkPair

    pair = ChunkPair(req_a="A", req_b="B", text_a="alpha", text_b="beta")
    candidate = to_candidate(pair, ComparisonResult(conflicts=True))
    assert candidate.evidence_quote_a == "alpha" and candidate.source == "llm_comparator"
    assert comparator_prompt(pair).startswith("Requirement A:")


# ─── Audit oracle: full pipeline recovers all 15, rejects near-misses ────────
def test_audit_oracle_recovers_all_conflicts(
    store: SqliteStore,
    true_pairs: set[frozenset[str]],
    near_miss_pairs: set[frozenset[str]],
) -> None:
    """An oracle LLM (confirms iff the pair is truly a conflict) lets the pipeline
    recover all 15 seeded conflicts and reject the near-misses — proving the wiring,
    independent of any real model's judgement quality."""

    def oracle(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        ids = re.findall(r"Requirement (\S+?):", _prompt_text(messages))
        is_true = len(ids) >= 2 and frozenset(ids[:2]) in true_pairs
        if "conflicts" in _output_props(info):  # comparator
            return _final(
                info,
                {
                    "conflicts": is_true,
                    "evidence_quote_a": "",
                    "evidence_quote_b": "",
                    "rationale": "",
                },
            )
        return _final(  # critic
            info,
            {"is_conflict": is_true, "confidence": 1.0 if is_true else 0.0, "rationale": "oracle"},
        )

    settings = Settings()
    report, trace = run_audit(store, settings, model=FunctionModel(oracle), use_llm=True)
    found = {frozenset((f.candidate.req_a, f.candidate.req_b)) for f in report.findings}
    assert true_pairs <= found, f"missed {true_pairs - found}"
    assert not (near_miss_pairs & found), near_miss_pairs & found
    # Rule candidates bypass the Critic; only the comparator's candidates are reviewed.
    critic_step = next(s for s in trace.steps if s.name == "critic")
    assert critic_step.detail["rule_bypassed"] == len(deterministic_candidates(store))


def test_rule_candidates_bypass_the_critic(
    store: SqliteStore, true_pairs: set[frozenset[str]]
) -> None:
    """A Critic that rejects everything must not touch the deterministic findings:
    numeric/superseded candidates are high-precision by construction and bypass it."""

    def reject_all(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if "conflicts" in _output_props(info):  # comparator: propose nothing
            return _final(info, {"conflicts": False})
        return _final(info, {"is_conflict": False, "confidence": 0.0, "rationale": "reject"})

    report, _trace = run_audit(store, Settings(), model=FunctionModel(reject_all), use_llm=True)
    found = {frozenset((f.candidate.req_a, f.candidate.req_b)) for f in report.findings}
    rule_pairs = {frozenset((c.req_a, c.req_b)) for c in deterministic_candidates(store)}
    # Every deterministic candidate survived despite the always-reject Critic.
    assert rule_pairs <= found
    assert len(true_pairs & found) >= 10
    assert all(f.verdict.confidence == 1.0 for f in report.findings)


def test_critic_filters_comparator_false_positives(
    store: SqliteStore, true_pairs: set[frozenset[str]], near_miss_pairs: set[frozenset[str]]
) -> None:
    """A comparator that confirms every pair, paired with a truth-oracle Critic:
    the Critic rejects the non-conflicts, so no near-miss reaches the findings."""

    def confirm_then_verify(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        ids = re.findall(r"Requirement (\S+?):", _prompt_text(messages))
        is_true = len(ids) >= 2 and frozenset(ids[:2]) in true_pairs
        if "conflicts" in _output_props(info):  # comparator: confirm everything
            return _final(info, {"conflicts": True})
        return _final(
            info,
            {"is_conflict": is_true, "confidence": 1.0 if is_true else 0.0, "rationale": "verify"},
        )

    report, _trace = run_audit(
        store, Settings(), model=FunctionModel(confirm_then_verify), use_llm=True
    )
    found = {frozenset((f.candidate.req_a, f.candidate.req_b)) for f in report.findings}
    assert report.rejected_by_critic >= 1  # the Critic filtered the confirmed non-conflicts
    assert not (near_miss_pairs & found)


def test_deterministic_audit_needs_no_model(
    store: SqliteStore, true_pairs: set[frozenset[str]]
) -> None:
    settings = Settings()
    report, _trace = run_audit(store, settings, model=None, use_llm=False)
    found = {frozenset((f.candidate.req_a, f.candidate.req_b)) for f in report.findings}
    # 10 numeric+superseded conflicts are recovered with no LLM at all.
    assert len(true_pairs & found) >= 10
    assert all(f.verdict.confidence == 1.0 for f in report.findings)


def test_usage_limits_from_settings() -> None:
    limits = usage_limits(Settings(max_agent_steps=7, max_tokens_per_run=1234))
    assert limits.request_limit == 7
    assert limits.total_tokens_limit == 1234
