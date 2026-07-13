"""Ingestion tests, including the Phase B Level-1 assertions.

These run on every commit (unmarked). They prove the parser faithfully recovers
the corpus, chunks and entities are well-formed, references resolve or are flagged,
and re-ingesting an unchanged corpus does nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from requirements_audit.cli import app
from requirements_audit.corpus import generator
from requirements_audit.ingestion.chunker import chunk_document
from requirements_audit.ingestion.extract import extract_entities, extract_refs
from requirements_audit.ingestion.parser import parse_corpus, parse_markdown
from requirements_audit.ingestion.pipeline import ingest_corpus
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import EntityType, Requirement, RequirementDocument

# Fields the Markdown format actually carries (category is not rendered).
_RECOVERABLE = (
    "id",
    "doc_id",
    "section",
    "title",
    "text",
    "parameters",
    "refs",
    "status",
    "superseded_by",
)


@pytest.fixture
def parsed_docs(generated_corpus: Path) -> list[RequirementDocument]:
    return parse_corpus(generated_corpus)


# ─── parser fidelity ─────────────────────────────────────────────────────────
def test_parser_recovers_generated_requirements(parsed_docs: list[RequirementDocument]) -> None:
    expected = {r.id: r for d in generator.build_documents() for r in d.requirements}
    actual = {r.id: r for d in parsed_docs for r in d.requirements}
    assert actual.keys() == expected.keys()
    for rid, exp in expected.items():
        got = actual[rid]
        for field in _RECOVERABLE:
            assert getattr(got, field) == getattr(exp, field), f"{rid}.{field} mismatch"


def test_parser_recovers_document_metadata(parsed_docs: list[RequirementDocument]) -> None:
    by_id = {d.id: d for d in parsed_docs}
    for gen_doc in generator.build_documents():
        assert by_id[gen_doc.id].title == gen_doc.title
        assert by_id[gen_doc.id].doc_type == gen_doc.doc_type


# ─── chunking ────────────────────────────────────────────────────────────────
def test_chunks_are_well_formed(parsed_docs: list[RequirementDocument]) -> None:
    for doc in parsed_docs:
        chunks = chunk_document(doc)
        assert len(chunks) == len(doc.requirements)  # one chunk per requirement
        for c in chunks:
            assert c.text.strip(), f"empty chunk {c.id}"
            assert c.requirement_id
            assert c.section_path and all(part.strip() for part in c.section_path)
            assert c.content_hash


# ─── extraction ──────────────────────────────────────────────────────────────
def test_every_requirement_gets_an_entity(parsed_docs: list[RequirementDocument]) -> None:
    for doc in parsed_docs:
        entities = extract_entities(doc)
        req_entities = {
            e.requirement_id for e in entities if e.entity_type is EntityType.REQUIREMENT
        }
        assert req_entities == {r.id for r in doc.requirements}


def test_parameter_entities_carry_values(parsed_docs: list[RequirementDocument]) -> None:
    for doc in parsed_docs:
        for e in extract_entities(doc):
            if e.entity_type is EntityType.PARAMETER:
                assert e.value is not None


def test_corpus_references_all_resolve(parsed_docs: list[RequirementDocument]) -> None:
    known = {r.id for d in parsed_docs for r in d.requirements}
    for doc in parsed_docs:
        for ref in extract_refs(doc, known):
            assert ref.resolved, f"unexpected dangling ref {ref.from_req} -> {ref.to_req}"


def test_dangling_reference_is_flagged() -> None:
    doc = RequirementDocument(
        id="X",
        title="X",
        doc_type="test",
        requirements=[
            Requirement(
                id="X-REQ-0001",
                doc_id="X",
                section="S",
                title="t",
                text="refers out",
                category="",
                refs=["X-REQ-9999"],
            )
        ],
    )
    refs = extract_refs(doc, known_ids={"X-REQ-0001"})
    assert len(refs) == 1
    assert refs[0].resolved is False


# ─── store + pipeline idempotency ─────────────────────────────────────────────
def test_ingest_is_idempotent(tmp_path: Path, generated_corpus: Path) -> None:
    db = tmp_path / "store.sqlite"
    with SqliteStore(db) as store:
        first = ingest_corpus(generated_corpus, store)
        assert first.new_docs and not first.updated_docs and not first.unchanged_docs
        chunks_after_first = first.chunks

        second = ingest_corpus(generated_corpus, store)
        assert not second.new_docs and not second.updated_docs
        assert len(second.unchanged_docs) == len(first.new_docs)
        assert second.chunks == chunks_after_first  # nothing re-written or duplicated


def test_ingest_totals_match_corpus(
    tmp_path: Path, generated_corpus: Path, parsed_docs: list[RequirementDocument]
) -> None:
    expected_chunks = sum(len(d.requirements) for d in parsed_docs)
    with SqliteStore(tmp_path / "s.sqlite") as store:
        report = ingest_corpus(generated_corpus, store)
        assert report.chunks == expected_chunks
        assert report.unresolved_refs == 0
        # every stored chunk round-trips with non-empty text
        assert all(c.text.strip() for c in store.all_chunks())


def test_updated_document_is_reprocessed(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    doc = corpus / "A.md"
    doc.write_text(
        "# Doc A\n\nDocument ID: A\nType: test\n\n## S\n\n"
        "### A-REQ-0001 — Title\n\nOriginal text.\n\n- Status: active\n",
        encoding="utf-8",
    )
    with SqliteStore(tmp_path / "s.sqlite") as store:
        r1 = ingest_corpus(corpus, store)
        assert r1.new_docs == ["A"]

        doc.write_text(
            "# Doc A\n\nDocument ID: A\nType: test\n\n## S\n\n"
            "### A-REQ-0001 — Title\n\nChanged text.\n\n- Status: active\n",
            encoding="utf-8",
        )
        r2 = ingest_corpus(corpus, store)
        assert r2.updated_docs == ["A"]
        assert store.all_chunks()[0].text == "Changed text."


# ─── CLI ─────────────────────────────────────────────────────────────────────
def test_cli_ingest_runs(tmp_path: Path, generated_corpus: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["ingest", str(generated_corpus), "--db", str(tmp_path / "cli.sqlite")]
    )
    assert result.exit_code == 0, result.output
    assert "new" in result.output
    assert "chunks" in result.output


def test_parse_markdown_handles_comma_in_parameter_value() -> None:
    md = (
        "# D\n\nDocument ID: D\nType: t\n\n## S\n\n"
        "### D-REQ-0001 — T\n\nbody\n\n- Status: active\n- Parameters: cyclic_tasks_ms = 10,50\n"
    )
    doc = parse_markdown(md)
    assert doc.requirements[0].parameters == {"cyclic_tasks_ms": "10,50"}
