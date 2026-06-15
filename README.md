# Requirements Audit

> A multi-agent system over engineering specification documents that answers requirement queries with citations and **detects contradictions between requirements across documents** — with a measured evaluation harness, not vibes.

**Status:** Phases A–C complete. `ingest`, `query`, and `audit` run from the CLI; the four-agent pipeline (Planner → Retriever → Analyst → Critic) is wired with LangFuse-style tracing. Contradiction recall on the numeric + superseded classes is gated in CI with no API keys; the prose (`incompatible_constraint`) class adds the LLM comparator. Eval harness, benchmarks, API/UI: Phases D–G.

---

## The problem

Engineering organizations accumulate hundreds of requirement documents — AUTOSAR specs, internal requirements, supplier constraints, derived requirements across versions. The same parameter appears in three places with three different values. A constraint is tightened in one document and loosened in another. By the time the conflict is found, it's already in production code.

Traditional tools (DOORS, Jira, Windchill) catalog requirements; they don't reason about them. The newer option — "ask an LLM to find contradictions" — produces plausible-looking answers with no way to know if they're right.

## The approach

Requirements Audit is a multi-agent pipeline over a hybrid retrieval index, with a dedicated contradiction-detection mode that finds conflicts across documents and surfaces them with quoted evidence from both sources.

Two design choices drive everything else:

1. **Contradiction detection is an orchestration problem, not a prompting problem.** A single LLM call asking "find contradictions across these documents" is unreliable. The pipeline instead pairs candidate requirements by shared entity, compares values and constraints, verifies the conflict against quoted sources, and rejects false positives before surfacing anything.

2. **Evaluation is the product.** The synthetic corpus is generated with a known number of seeded contradictions of known types — so contradiction precision and recall are measurable by construction, not estimated by vibes. Every prompt or code change runs through an eval gate in CI; regressions fail the build.

## Architecture

```
docs (ARXML, MD, PDF) ──► INGESTION (parse → structure-aware chunk → entity/ref extract)
                                   ├── Qdrant (hybrid: dense + BM25)
                                   └── SQLite (entities, refs, content-hash ledger)

                          ORCHESTRATOR (PydanticAI · typed state · budgets · loop caps)
   query / audit  ──►  Planner ──► Retriever ──► Analyst ──► Critic ──►  answer + citations
                       (route,     (tools:        (draft     (verify              OR
                        decompose)  hybrid_search, answer /   claims vs           finding report
                                    get_section,   pair reqs  sources;            + human gate
                                    find_refs)     & compare) reject FPs)

                          OPS:  LangFuse traces · cost/latency per run · FastAPI + SSE · Streamlit UI · Docker
                          EVAL: golden set + seeded contradictions · Ragas + LLM-judge
                                in pytest · GitHub Actions gate
```

**Agent roles**
- **Planner** — routes Q&A vs audit; decomposes complex queries.
- **Retriever** — typed tools over Qdrant: `hybrid_search`, `get_section`, `find_refs`.
- **Analyst** — drafts answers with inline citations; pairs requirements by shared entity for audit mode.
- **Critic** — verifies claims against quoted sources, rejects false positives, emits confidence.

## Why this beats a single LLM prompt

| Capability | Single-prompt LLM | Requirements Audit |
|---|---|---|
| Find contradictions across many docs | One shot — hallucinations possible | Pipeline pairs candidates, verifies against sources |
| Citations for both conflicting sources | Sometimes, unreliably | Always quoted, with source IDs |
| Precision / recall measurable | No ground truth → vibes | Seeded contradictions → numbers |
| Catches regressions before deploy | No | CI eval gate fails on faithfulness drop |
| Production observability | No | LangFuse traces, cost & latency per run |
| Human-in-the-loop gate on findings | No | Flagged contradictions surface for review |

## Evaluation methodology

This project enacts [Hamel Husain's L1/L2/L3 evals doctrine](https://hamel.dev/blog/posts/evals/):

- **L1 — assertions:** output schema, citation presence, tool-call shape, no-internal-fields-leak. Runs on every commit.
- **L2 — human + model evals:** golden-question set with expected sources; Ragas faithfulness, answer relevancy, context precision; LLM-judge with **precision/recall calibrated against hand-labeled items** rather than raw agreement. Runs nightly and in CI.
- **L3 — A/B tests:** out of MVP scope; documented in the roadmap.

The eval gate runs in two tiers (thresholds live in `evals/thresholds.yaml`):

- **Every commit, no API keys** (`pytest -m eval` in CI): retrieval `precision@k`/`recall@k` on the golden set, deterministic contradiction recall (numeric + superseded), and the L1 assertions. A retrieval or rule regression fails the build immediately.
- **Nightly / on demand, with keys** (`.github/workflows/eval-nightly.yml`): Ragas faithfulness/answer_relevancy/context_precision, the calibrated LLM-judge, and the full contradiction recall + before-vs-after-Critic precision. This is where a faithfulness or recall drop fails the build.

The LLM-judge is calibrated against `evals/judge_labels.json` (30 items) and reported as precision/recall, not raw agreement. Those labels are **construction-derived from the synthetic corpus** (seeded conflicts → yes, near-misses and clearly-unrelated pairs → no), not blind third-party human labels — the same synthetic-corpus tradeoff disclosed above, chosen so the calibration number is reproducible and versioned.

## Numbers (to be filled by benchmarking phase)

| Metric | Value |
|---|---|
| Context precision@5 — naive vs hybrid vs hybrid+rerank | _TBD_ |
| Ragas faithfulness on golden set | _TBD_ |
| Contradiction precision / recall — before vs after Critic | _TBD_ |
| False-positive rate eliminated by Critic stage | _TBD_ |
| Cost per query / per full audit (Anthropic vs OpenAI) | _TBD_ |
| p95 latency per agent stage | _TBD_ |

## Quickstart

```bash
uv sync                                 # install pinned deps
cp .env.example .env                    # add API keys (needed for query + full audit)
requirements-audit ingest corpus/       # build the index (no keys needed)
requirements-audit audit --no-llm       # deterministic sweep: numeric + superseded conflicts, no keys
requirements-audit query "What is the watchdog timeout?"   # Q&A with citations (needs a key)
requirements-audit audit                # full sweep incl. prose conflicts (needs a key)

make ui                                 # optional: launch the Streamlit UI (Phase G)
```

`audit --no-llm` and the whole eval gate run offline; `query` and the full `audit`
call an LLM (Anthropic primary, OpenAI fallback) and require an API key.

The CLI is the primary interface; a lightweight **Streamlit UI** (a thin client over the same API) offers the same ingest / query / audit flows for non-terminal use and the demo.

## Scope

**In scope for the MVP:**
- Multi-format ingestion (ARXML, Markdown, PDF) with structure-aware chunking
- Hybrid retrieval (dense + BM25) over Qdrant; SQLite entity / reference tables
- Four-agent pipeline (Planner → Retriever → Analyst → Critic) in PydanticAI
- Evaluation harness with golden set, contradiction ground truth, Ragas, calibrated LLM-judge, CI gate
- FastAPI + SSE, Docker compose, LangFuse tracing, provider fallback (Anthropic ↔ OpenAI)
- Streamlit UI — a thin client over the API for ingest, query, and audit

**Deliberately out of scope (roadmap):**
- Graph store (Neo4j) — SQLite reference tables cover contradiction pairing at MVP scale
- Heavyweight custom frontend (SPA) — the CLI is primary and a lightweight Streamlit UI covers visual use
- n8n folder/webhook ingestion automation — paused, revisit post-MVP
- Fine-tuning, self-hosted models, authentication, multi-tenancy

## Repository layout

```
requirements-audit/
├── src/requirements_audit/   # ingestion, agents, tools, retrieval, llm, api, ui
├── evals/                    # golden_set.json, contradictions.json, test_*.py
├── corpus/                   # synthetic requirements + public AUTOSAR excerpts
├── .github/workflows/ci.yml  # lint → unit → eval gate → build
├── docker-compose.yml        # api + qdrant + langfuse
└── README.md
```

## License

TBD — will be MIT.
