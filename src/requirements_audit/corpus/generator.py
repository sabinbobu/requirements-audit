"""Deterministic corpus + ground-truth generator.

Lays the seeded requirements from `spec.py` into documents, pads each document
with deterministically generated filler, and writes:
  - corpus/<DOC>.md          one Markdown file per document
  - evals/contradictions.json  15 true + 5 near-miss labeled cases
  - evals/golden_set.json      50 graded Q&A items across all six scenarios

No network, no LLM, fixed RNG seed -> regenerates byte-identical output.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from requirements_audit.corpus import spec
from requirements_audit.models import (
    Contradiction,
    GoldenQuestion,
    Requirement,
    RequirementDocument,
    RequirementStatus,
    ScenarioTag,
)

SEED = 20260615

# Project root = three levels up from this file (src/requirements_audit/corpus/).
_ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = _ROOT / "corpus"
EVALS_DIR = _ROOT / "evals"

# Qualitative filler templates — deliberately number-free so filler can never
# accidentally collide with a seeded parameter and create a phantom contradiction.
_FILLER_SUBJECTS = (
    "The diagnostic manager",
    "The communication stack",
    "The power management module",
    "The application software",
    "The bootloader",
    "The supervision logic",
    "The network management layer",
    "The non-volatile memory handler",
)
_FILLER_PREDICATES = (
    "shall log a status event when the operating mode changes",
    "shall report its health to the system supervisor each cycle",
    "shall expose its configuration through the standard diagnostic interface",
    "shall persist its state across a controlled reset",
    "shall raise a warning when an inconsistent configuration is detected",
    "shall be verifiable through the integration test harness",
    "shall follow the layered architecture defined for this ECU",
    "shall document its interface in the released specification",
)


def _seed_requirements() -> list[Requirement]:
    """All hand-authored requirements (seeded conflict pairs + Q&A anchors), de-duplicated."""
    seen: dict[str, Requirement] = {}
    for s in spec.SEEDS:
        for req in (s.req_a, s.req_b):
            seen.setdefault(req.id, req)
    for anchor in spec.ANCHORS:
        seen.setdefault(anchor.requirement.id, anchor.requirement)
    # Deterministic order: by id.
    return [seen[k] for k in sorted(seen)]


def _generate_filler(authored: list[Requirement], rng: random.Random) -> list[Requirement]:
    needed = spec.FILLER_TARGET_TOTAL - len(authored)
    if needed <= 0:
        return []
    docs = list(spec.DOCUMENTS)
    counters = dict.fromkeys(docs, spec.FILLER_ID_START)
    existing_ids = [r.id for r in authored]
    filler: list[Requirement] = []
    for i in range(needed):
        doc = docs[i % len(docs)]
        _title, _doc_type, sections = spec.DOCUMENTS[doc]
        n = counters[doc]
        counters[doc] += 1
        rid = f"{doc}-REQ-{n:04d}"
        section = sections[n % len(sections)]
        subject = rng.choice(_FILLER_SUBJECTS)
        predicate = rng.choice(_FILLER_PREDICATES)
        refs: list[str] = []
        if rng.random() < 0.3 and existing_ids:
            refs = [rng.choice(existing_ids)]
        filler.append(
            Requirement(
                id=rid,
                doc_id=doc,
                section=section,
                title=f"{subject.removeprefix('The ').capitalize()} behavior",
                text=f"{subject} {predicate}.",
                category="general",
                refs=refs,
            )
        )
        existing_ids.append(rid)
    return filler


def build_documents() -> list[RequirementDocument]:
    rng = random.Random(SEED)
    reqs = _seed_requirements()
    reqs = reqs + _generate_filler(reqs, rng)

    documents: list[RequirementDocument] = []
    for doc_id, (title, doc_type, sections) in spec.DOCUMENTS.items():
        doc_reqs = [r for r in reqs if r.doc_id == doc_id]
        # Order by section (spec order), then by id, for stable rendering.
        section_rank = {name: idx for idx, name in enumerate(sections)}
        doc_reqs.sort(key=lambda r: (section_rank.get(r.section, 99), r.id))
        documents.append(
            RequirementDocument(id=doc_id, title=title, doc_type=doc_type, requirements=doc_reqs)
        )
    return documents


def build_contradictions() -> list[Contradiction]:
    return [
        Contradiction(
            id=s.conflict_id,
            req_a=s.req_a.id,
            req_b=s.req_b.id,
            conflict_type=s.conflict_type,
            evidence_quote_a=s.evidence_quote_a,
            evidence_quote_b=s.evidence_quote_b,
            rationale=s.rationale,
            is_true_conflict=s.is_true_conflict,
        )
        for s in spec.SEEDS
    ]


def build_golden_set() -> list[GoldenQuestion]:
    questions: list[GoldenQuestion] = []

    # success — one per clean anchor.
    for anchor in spec.ANCHORS:
        questions.append(
            GoldenQuestion(
                id="",
                question=anchor.question,
                expected_source_ids=[anchor.requirement.id],
                expected_facts=list(anchor.facts),
                scenario=ScenarioTag.SUCCESS,
            )
        )

    # contradictory_result — one per true contradiction (both sources expected).
    for s in spec.SEEDS:
        if not s.is_true_conflict:
            continue
        questions.append(
            GoldenQuestion(
                id="",
                question=f"Is there a conflict regarding {_topic(s.req_a.title)}?",
                expected_source_ids=[s.req_a.id, s.req_b.id],
                expected_facts=[],
                scenario=ScenarioTag.CONTRADICTORY_RESULT,
            )
        )

    questions.extend(spec.MULTI_QUESTIONS)
    questions.extend(spec.EDGE_QUESTIONS)

    # Assign stable sequential ids.
    return [q.model_copy(update={"id": f"GQ-{i:04d}"}) for i, q in enumerate(questions, start=1)]


def _topic(title: str) -> str:
    return title[0].lower() + title[1:]


def render_markdown(doc: RequirementDocument) -> str:
    lines = [f"# {doc.title}", "", f"Document ID: {doc.id}", f"Type: {doc.doc_type}", ""]
    current_section = None
    for req in doc.requirements:
        if req.section != current_section:
            current_section = req.section
            lines += [f"## {current_section}", ""]
        lines.append(f"### {req.id} — {req.title}")
        lines.append("")
        lines.append(req.text)
        lines.append("")
        meta = [f"- Status: {req.status.value}"]
        if req.status is RequirementStatus.SUPERSEDED and req.superseded_by:
            meta.append(f"- Superseded by: {req.superseded_by}")
        if req.refs:
            meta.append(f"- References: {', '.join(req.refs)}")
        if req.parameters:
            params = ", ".join(f"{k} = {v}" for k, v in req.parameters.items())
            meta.append(f"- Parameters: {params}")
        lines += meta
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _dump_json(path: Path, payload: list[object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def generate() -> None:
    """Write the corpus and both ground-truth files. Idempotent and deterministic."""
    documents = build_documents()
    contradictions = build_contradictions()
    questions = build_golden_set()

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    EVALS_DIR.mkdir(parents=True, exist_ok=True)

    for doc in documents:
        (CORPUS_DIR / f"{doc.id}.md").write_text(render_markdown(doc), encoding="utf-8")

    _dump_json(
        EVALS_DIR / "contradictions.json",
        [c.model_dump(mode="json") for c in contradictions],
    )
    _dump_json(
        EVALS_DIR / "golden_set.json",
        [q.model_dump(mode="json") for q in questions],
    )

    total_reqs = sum(len(d.requirements) for d in documents)
    true_conflicts = sum(1 for c in contradictions if c.is_true_conflict)
    print(
        f"Generated {len(documents)} documents, {total_reqs} requirements, "
        f"{true_conflicts} true contradictions + {len(contradictions) - true_conflicts} "
        f"near-misses, {len(questions)} golden questions."
    )
