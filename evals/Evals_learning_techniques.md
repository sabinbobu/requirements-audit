## 1. Learning: Map your AI product surface area 8/10

Output applied for current project specs:
- Define the product surface as three primary flows already present in the repo: `ingest`, `query`, and `audit`.
- Split `query` into explicit scenarios: correct answer with citations, answer with partial retrieval, no relevant context found, ambiguous user question, and invalid query format.
- Split `audit` into two modes: deterministic (`--no-llm`) and full LLM comparator mode, each with success/failure scenarios per contradiction type (`numeric_mismatch`, `superseded_requirement`, `incompatible_constraint`).
- Split `ingest` into document-type and integrity scenarios: Markdown success, ARXML success, parse failure, duplicate content hash, and missing/invalid document metadata.
- Keep this scenario map as a living matrix in the repo docs so each scenario can be tied to at least one eval test.

Scoring commentary: Coverage is strong across the three core flows and major failure modes, but the score is not higher because a formal, continuously maintained scenario matrix is still a target state rather than clearly institutionalized practice.

How to improve:
- Create `docs/eval-scenario-matrix.md` with rows for each `ingest`, `query`, and `audit` scenario and columns for owner, test coverage, and risk.
- Add a CI check that fails when a scenario marked as "required" has no linked eval test.
- Update the matrix in every feature PR with one explicit line: new scenario added, existing scenario changed, or no scenario impact.
- Add edge cases currently missing in the matrix: malformed ARXML structure, citation tie-breaks, and cross-document synonym conflicts.

## 2. Learning: Create Level 1 evals first 9/10

Output applied for current project specs:
- Keep L1 as the default gate in CI using the existing `pytest -m eval` path in `.github/workflows/ci.yml`.
- Enforce deterministic assertions already aligned with the repo: output schema validity, citation presence, no internal field leakage, tool-call shape, valid identifiers, and expected count constraints.
- Keep contradiction deterministic recall checks mandatory in L1 using the existing `deterministic_recall_min` threshold in `evals/thresholds.yaml`.
- Ensure each new CLI or agent output field gets an assertion before it is treated as stable behavior.

Scoring commentary: This is one of the most mature areas in the repo, with clear deterministic assertions and CI gating already in place; the remaining gap is mainly around expanding assertion depth as features evolve.

How to improve:
- Add a mandatory PR checklist item: "Any output contract change includes a new or updated L1 assertion."
- Extend L1 checks to validate citation span correctness (source ID plus quoted snippet) rather than citation presence only.
- Add negative assertions for forbidden leak fields in every API/CLI response shape test.
- Introduce a small set of deterministic robustness tests for tool-call argument validation and invalid ID handling.

## 3. Learning: Generate and maintain test cases 8/10

Output applied for current project specs:
- Continue combining synthetic ground truth and realistic prompts via existing fixtures in `evals/golden_set.json`, `evals/contradictions.json`, and `evals/judge_labels.json`.
- Add at least one new eval case whenever a bug is found in `query` or `audit` so failures become regression-protected.
- Version test case expansions with explicit rationale in PR descriptions (for example: "added near-miss contradiction pair to reduce false positives").
- Keep corpus-integrity checks in `tests/test_corpus_integrity.py` and ensure new corpus files are validated before merge.

Scoring commentary: The repo already has a strong dataset and test asset foundation, but the score reflects that failure-driven expansion rules are described well and should be enforced more systematically in day-to-day contribution flow.

How to improve:
- Add `evals/CHANGELOG.md` to record each new case with failure class, root cause, and linked fix PR.
- Enforce a contribution rule: every production bug fix touching retrieval, generation, or contradiction logic must add at least one eval case.
- Expand `evals/judge_labels.json` with harder borderline pairs and near-miss negatives each release cycle.
- Add a dataset freshness check that reports case counts by class and flags imbalances.

## 4. Learning: Run evals automatically 9/10

Output applied for current project specs:
- Preserve the current two-tier automation model:
	- Per-commit CI gate for deterministic evals and retrieval checks (no API key required).
	- Nightly or on-demand live evals for Ragas + LLM judge + full contradiction pipeline.
- Keep threshold management centralized in `evals/thresholds.yaml` so quality bars are changed via configuration review, not hidden test logic edits.
- Record run metadata per eval execution: code revision, thresholds revision, dataset revision, model/provider used, and run mode (`no-llm` vs full).
- Fail builds on threshold regressions to maintain "evaluation as product" discipline.

Scoring commentary: Automation is robust with clear CI gates and threshold-based control, and the only meaningful gap is improving visibility and historical reporting of run metadata across time.

How to improve:
- Publish eval artifacts in CI: thresholds used, metric outputs, and failing-case summaries as downloadable workflow artifacts.
- Add a scheduled job that writes a compact trend snapshot (last 10 runs) to `docs/superpowers/eval-metrics-trend.md`.
- Tag each run with dataset hash and model/provider in a machine-readable JSON report for reproducibility.
- Add alerting for repeated threshold-near misses (for example, three consecutive runs within 5% of floor values).

## 5. Learning: Instrument trace logging 7/10

Output applied for current project specs:
- Use LangFuse-style tracing already described in the repo to capture full pipeline telemetry.
- Standardize trace fields per run: user input, planner route decision, retriever tool calls, retrieved chunks/sections, analyst draft claims, critic verification outcomes, latency, errors, and final answer/findings.
- Add stable correlation IDs so each CLI/API request can be joined with eval outcomes and contradiction metrics.
- Keep trace payloads searchable by scenario type (for example: `audit.full.incompatible_constraint`) to accelerate root-cause analysis.

Scoring commentary: Tracing capability exists and is architecturally planned, but the score is moderated because standardized telemetry conventions and reliable correlation workflows are not yet fully demonstrated as routine.

How to improve:
- Define a trace schema document in `docs/superpowers/trace-schema.md` with required fields and allowed enums.
- Add correlation IDs to CLI/API entrypoints and propagate them through Planner, Retriever, Analyst, and Critic stages.
- Implement a trace completeness test that fails when required fields are missing from sampled runs.
- Add a simple trace-to-eval join script under `evals/` to link failing cases to their run traces.

## 6. Learning: Review data on a cadence 5/10

Output applied for current project specs:
- Establish a recurring eval review rhythm (weekly lightweight review, monthly deeper quality review).
- Start with binary tagging (`pass/fail`, `acceptable/not acceptable`) on sampled traces before introducing fine-grained rubrics.
- Prioritize review queues by risk: contradiction misses first, false-positive contradiction flags second, low-faithfulness query answers third.
- Track trends over time for `precision@k`, `recall@k`, deterministic contradiction recall, and live faithfulness metrics.

Scoring commentary: The technical signals exist, but evidence of a consistent operating cadence and documented review rituals is limited, so this area remains mid-maturity and process-dependent.

How to improve:
- Create a recurring weekly "Eval Triage" issue template in `.github/ISSUE_TEMPLATE/` with fixed review inputs and outputs.
- Add a monthly quality review document in `docs/superpowers/monthly-eval-review.md` capturing trends, top regressions, and decisions.
- Define ownership rotation for eval review so cadence does not depend on one contributor.
- Track and publish action completion rate from review findings to ensure reviews lead to implemented fixes.

## 7. Learning: Align automated judges with humans 7/10

Output applied for current project specs:
- Continue calibration of model-judge outputs against labeled data in `evals/judge_labels.json`.
- Report judge quality as precision/recall (not just agreement), especially because positive failures are relatively sparse.
- Expand label sets when new failure patterns are discovered (for example, subtle contradiction phrasing or citation-supported but incorrect conclusions).
- Use human adjudication on disagreement buckets to refine prompts/rubrics for `evals/test_judge.py`.

Scoring commentary: Calibration intent and artifacts are present, but a larger and more continuously refreshed adjudication loop is needed to push judge reliability closer to production-grade confidence.

How to improve:
- Expand `evals/judge_labels.json` to a larger labeled pool with balanced positive/negative and ambiguity-heavy samples.
- Add a periodic calibration test that reports judge precision/recall by failure subtype, not only aggregate.
- Create a disagreement queue where low-confidence or mismatched items require manual adjudication before closing.
- Version judge rubric prompts and evaluate rubric changes against a locked calibration slice before adoption.

## 8. Learning: Use eval data for improvement 6/10

Output applied for current project specs:
- Treat each failed eval as a tracked backlog item mapped to one fix lane: prompt update, retriever tuning, contradiction rule/comparator update, citation policy tightening, or corpus/test expansion.
- Require "fix + new test" closure for recurring failure classes.
- Use deterministic failures to prioritize fast reliability work; use live metric drops to prioritize model/prompt/context-quality work.
- Keep improvement artifacts discoverable by linking PRs to the exact failing test names and threshold breaches.

Scoring commentary: The improvement model is well-defined, but the score reflects that the closed-loop discipline from failed eval to tracked remediation to test hardening is not yet uniformly visible across all change cycles.

How to improve:
- Add a `quality-backlog` label in GitHub and auto-create issues from failing eval jobs with metric and test context.
- Require each eval-driven fix PR to include links to the originating failure and the new/updated regression test.
- Track lead time from eval failure to merged fix as a quality KPI.
- Create a quarterly cleanup pass to retire flaky or redundant evals and replace them with higher-signal tests.

## 9. Learning: Add A/B testing when ready 3/10

Output applied for current project specs:
- Introduce A/B only after offline and live thresholds remain stable for several consecutive runs.
- Start with low-risk toggles already natural to this architecture: retrieval strategy variants, rerank variants, critic strictness variants, and prompt-template variants.
- Define business/engineering success metrics before rollout: contradiction precision uplift, contradiction recall stability, citation correctness, user resolution rate, and latency/cost envelope.
- Roll out in controlled slices and keep a hard rollback condition when contradiction false positives or faithfulness regress beyond agreed thresholds.

Scoring commentary: This is mostly a readiness and roadmap topic in the current version; architecture supports future experiments, but execution-level A/B infrastructure and operational practice are still early.

How to improve:
- Add an experiment config file (for example `evals/experiments.yaml`) to define variants, traffic split, success metrics, and rollback rules.
- Implement variant toggles for retrieval strategy and critic strictness behind explicit feature flags.
- Build an experiment report script that compares precision, recall, faithfulness, latency, and cost between A and B runs.
- Run a limited-scope pilot on a fixed golden subset first, then scale only if guardrail metrics remain within thresholds.

