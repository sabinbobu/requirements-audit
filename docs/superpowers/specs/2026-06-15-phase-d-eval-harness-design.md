# Phase D — Eval Harness: Design

> Status: approved 2026-06-15. Implements Project_plan.md Phase D (Days 8–9).
> Branch: `feat/phase-d-eval-harness`. Builds on Phase C (agent core).

## Goal

Turn the existing ground truth (50 golden questions + 15 seeded contradictions +
5 near-misses) into a measured eval harness that gates regressions in CI and
produces the senior-signal numbers (retrieval P/R, faithfulness, contradiction
precision/recall before vs after Critic, calibrated LLM-judge).

## Decisions locked in brainstorming

1. **Two-tier eval, mirroring Phase C.** Deterministic metrics gate every commit
   with no API keys; Ragas + LLM-judge + full/before-after-Critic contradiction
   metrics run live/nightly (skipped without keys).
   - **Gate (no keys, every commit):** retrieval `precision@k`/`recall@k` on the
     golden set; deterministic contradiction recall (numeric + superseded) ≥ 10/10;
     L1 assertions (citation presence, output schema, requirement-ID format).
   - **Live (keys, nightly/on-demand):** Ragas faithfulness / answer_relevancy /
     context_precision; LLM-judge precision/recall vs labels; full contradiction
     recall and the before-vs-after-Critic precision lift.
2. **Construction-derived judge labels.** A versioned `evals/judge_labels.json`
   (~30 contradiction-judgement items drawn from the seeded ground truth: true
   conflicts → yes, near-misses → no, plus clear non-conflicts → no). The harness
   reports judge precision/recall/agreement against these. The README discloses
   they are construction-derived from the synthetic corpus, not blind third-party
   human labels — the same synthetic-corpus tradeoff already disclosed.

## Components

### Metric library — `src/requirements_audit/eval/` (pure, unit-testable)

- **`retrieval.py`** — `precision_at_k(expected, retrieved, k)`,
  `recall_at_k(...)`, and `evaluate_retrieval(store, questions, k)` returning
  mean P@k/R@k over questions that have `expected_source_ids` (scenarios:
  success, contradictory_result, multi_result). Uses the Phase C BM25 index.
- **`contradiction.py`** — `score(found_pairs, ground_truth)` →
  precision/recall/FP-rate against the 15 true + 5 near-miss pairs. Pure set math;
  fed either the deterministic candidate set (gate) or the full pipeline output
  before and after the Critic (live).
- **`judge.py`** — a PydanticAI LLM judge with an explicit rubric (typed verdict),
  and `calibrate(judge, labels)` → precision/recall/agreement vs `judge_labels.json`.
  Live only.
- **`ragas_eval.py`** — builds the `(question, answer, contexts, ground_truth)`
  dataset from `answer_query` runs and calls Ragas faithfulness / answer_relevancy /
  context_precision. Imported lazily (eval extra). Live only.
- **`thresholds.py`** — loads `evals/thresholds.yaml` into a typed `Thresholds`
  model (`gate` + `live` sections). Adds `pyyaml` as a dependency (`uv lock`).

### Data / config

- **`evals/thresholds.yaml`** — `gate`: retrieval P@k/R@k floors, deterministic
  contradiction recall floor (10). `live`: faithfulness floor, full contradiction
  recall floor (11), judge precision/recall floors.
- **`evals/judge_labels.json`** — ~30 labeled judgement items.

### Tests (`-m eval`, the CI eval stage)

- **Deterministic, run in CI (no keys):** `evals/test_retrieval.py`,
  `evals/test_contradiction.py`, `evals/test_assertions.py` — assert against
  `thresholds.yaml.gate`.
- **Live, auto-skip without keys/ragas:** `evals/test_generation.py` (Ragas),
  `evals/test_judge.py`. A `requires_llm` skip guard checks for an API key and the
  ragas import; in keyless CI they skip, keeping the eval stage green.
- **`evals/conftest.py`** — ingested in-memory store, ground-truth, and thresholds
  fixtures (mirrors `tests/conftest.py`).
- Remove `evals/test_placeholder.py`.

### CI

- The existing `pytest -m eval` stage becomes a real gate: deterministic evals now
  fail the build on retrieval or deterministic-contradiction regressions.
- **`.github/workflows/eval-nightly.yml`** — schedule + `workflow_dispatch`; syncs
  the eval group, uses an `ANTHROPIC_API_KEY` repo secret, runs the live evals
  (Ragas, judge, full/before-after-Critic). This is where the "bad-prompt PR fails
  CI" demo artifact lives. The workflow is scaffolded here; producing the actual
  failing PR + Loom (needs the key) stays a manual portfolio step.

## Scope boundary

Because faithfulness and the judge are live-only, the *every-commit* gate fails on
retrieval and deterministic-contradiction regressions. The plan's "faithfulness
drops >5%" / full-recall thresholds are enforced in the nightly/live job, not in
keyless PR CI. This is the deliberate consequence of the key-free CI ethos.

## Out of scope (later phases)

Chunk-size / hybrid-variant benchmark sweep and cost/latency tables (Phase E);
FastAPI/SSE (F); Streamlit UI (G).
