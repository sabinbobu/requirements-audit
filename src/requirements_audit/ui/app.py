"""Streamlit UI — a thin client over the FastAPI endpoints.

Scope rule (Project_plan Phase G): this app re-implements NO pipeline logic.
Every action is an HTTP call through `ui.client.ApiClient`; the API stays the
single source of truth that the CLI and this UI both sit on. Rendering only.

Run with:  make ui            (API base URL from REQUIREMENTS_AUDIT_API, default
                               http://localhost:8000 — start it with `make api`)
"""

from __future__ import annotations

import os
from typing import Any, cast

import streamlit as st

from requirements_audit.ui.client import ApiClient, ApiError

st.set_page_config(page_title="Requirements Audit", page_icon="📋", layout="wide")


def api() -> ApiClient:
    # Session-state memo rather than @st.cache_resource: one client per session,
    # and no untyped-decorator friction under mypy --strict.
    if "api_client" not in st.session_state:
        st.session_state["api_client"] = ApiClient(
            base_url=os.environ.get("REQUIREMENTS_AUDIT_API", "http://localhost:8000")
        )
    return cast(ApiClient, st.session_state["api_client"])


# ─── sidebar: connection status ───────────────────────────────────────────────
with st.sidebar:
    st.title("Requirements Audit")
    try:
        health = api().health()
        st.success(f"API ok · v{health['version']} · {health['chunks']} chunks indexed")
    except (ApiError, Exception) as exc:
        st.error(f"API unreachable: {exc}")
        st.caption("Start it with `make api` (or `docker compose up -d`).")
    st.caption("Thin client over the FastAPI endpoints — no pipeline logic runs in this UI.")

ingest_tab, query_tab, audit_tab = st.tabs(["Ingest", "Query", "Audit"])


# ─── ingest view ──────────────────────────────────────────────────────────────
with ingest_tab:
    st.subheader("Ingest a corpus")
    corpus_dir = st.text_input(
        "Corpus directory (path on the API host)", value="corpus/", key="corpus_dir"
    )
    if st.button("Run ingest", type="primary"):
        try:
            with st.spinner("Ingesting…"):
                report = api().ingest(corpus_dir)
        except ApiError as exc:
            st.error(exc.detail)
        else:
            new, updated, unchanged = (
                report["new_docs"],
                report["updated_docs"],
                report["unchanged_docs"],
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("New docs", len(new))
            c2.metric("Updated docs", len(updated))
            c3.metric("Unchanged docs", len(unchanged))
            st.write(
                f"Store now holds **{report['chunks']} chunks**, "
                f"{report['entities']} entities, {report['refs']} references "
                f"({report['unresolved_refs']} unresolved)."
            )
            if unchanged and not new and not updated:
                st.info("Ledger hit: content hashes unchanged, nothing re-indexed.")


# ─── query view ───────────────────────────────────────────────────────────────
with query_tab:
    st.subheader("Ask a question")
    question = st.text_input(
        "Question", placeholder="What is the watchdog timeout?", key="question"
    )
    if st.button("Ask", type="primary", disabled=not question):
        stages = st.status("Running the pipeline…", expanded=True)
        answer: dict[str, Any] | None = None
        trace: dict[str, Any] | None = None
        try:
            for event, payload in api().query_stream(question):
                if event == "stage" and isinstance(payload, dict):
                    stages.write(f"✓ {payload['name']} · {payload['latency_ms']:.0f} ms")
                elif event == "answer" and isinstance(payload, dict):
                    answer = payload
                elif event == "trace" and isinstance(payload, dict):
                    trace = payload
                elif event == "error":
                    stages.update(label="Pipeline failed", state="error")
                    st.error(str(payload))
        except ApiError as exc:
            stages.update(label="Request rejected", state="error")
            # 503 = no LLM key configured server-side; relay the guidance as-is.
            st.error(exc.detail)
        if answer is not None:
            stages.update(label="Done", state="complete", expanded=False)
            st.markdown(answer["text"])
            citations = answer.get("citations", [])
            if citations:
                st.markdown("**Sources**")
                for citation in citations:
                    with st.expander(f"{citation['doc_id']} · {citation['requirement_id']}"):
                        st.write(citation["quote"])
            else:
                st.warning("No supporting sources in the corpus (honest no-result).")
        if trace is not None:
            st.caption(f"Total latency: {trace['total_latency_ms']:.0f} ms")


# ─── audit view ───────────────────────────────────────────────────────────────
with audit_tab:
    st.subheader("Contradiction sweep")
    mode = st.radio(
        "Comparator mode",
        ["auto", "deterministic only", "force LLM"],
        horizontal=True,
        help="auto = LLM comparator + Critic when the API has a key, deterministic otherwise.",
    )
    use_llm = {"auto": None, "deterministic only": False, "force LLM": True}[mode]
    if st.button("Run audit", type="primary"):
        try:
            with st.spinner("Sweeping the corpus…"):
                st.session_state["audit_report"] = api().audit(use_llm)
        except ApiError as exc:
            st.error(exc.detail)

    audit_report: dict[str, Any] | None = st.session_state.get("audit_report")
    if audit_report:
        st.write(
            f"**{len(audit_report['findings'])} finding(s)** from "
            f"{audit_report['candidates_considered']} candidate(s); "
            f"{audit_report['rejected_by_critic']} rejected by the Critic. "
            f"LLM used: {'yes' if audit_report['llm_used'] else 'no (deterministic classes only)'}. "
            f"Latency: {audit_report['trace']['total_latency_ms']:.0f} ms."
        )
        # Human-review gate: accept/dismiss lives in this session; persisting
        # review decisions through the API is a roadmap item, and the UI says so.
        st.caption("Review decisions below are session-only (persistence: roadmap).")
        for i, finding in enumerate(audit_report["findings"]):
            candidate, verdict = finding["candidate"], finding["verdict"]
            title = (
                f"[{candidate['conflict_type']}] {candidate['req_a']} ↔ {candidate['req_b']} "
                f"(confidence {verdict['confidence']:.2f})"
            )
            with st.expander(title):
                st.markdown(f"**A — {candidate['req_a']}:** {candidate['evidence_quote_a']}")
                st.markdown(f"**B — {candidate['req_b']}:** {candidate['evidence_quote_b']}")
                st.caption(verdict["rationale"])
                decision_key = f"decision_{i}"
                c1, c2, c3 = st.columns([1, 1, 6])
                if c1.button("Accept", key=f"accept_{i}"):
                    st.session_state[decision_key] = "accepted"
                if c2.button("Dismiss", key=f"dismiss_{i}"):
                    st.session_state[decision_key] = "dismissed"
                decision = st.session_state.get(decision_key, finding["human_status"])
                c3.write(f"Status: **{decision}**")
