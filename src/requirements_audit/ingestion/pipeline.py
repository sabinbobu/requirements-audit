"""Ingestion pipeline: parse -> chunk -> extract -> store, with idempotent re-runs.

A document is re-processed only when its content hash changed since the last run,
so re-ingesting an unchanged corpus reports everything as unchanged and writes
nothing. The returned report carries both the store-wide totals and the per-run
ledger delta (new / updated / unchanged documents).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from requirements_audit.ingestion.chunker import chunk_document, content_hash
from requirements_audit.ingestion.extract import extract_entities, extract_refs
from requirements_audit.ingestion.parser import parse_markdown
from requirements_audit.ingestion.store import SqliteStore


class IngestReport(BaseModel):
    new_docs: list[str] = Field(default_factory=list)
    updated_docs: list[str] = Field(default_factory=list)
    unchanged_docs: list[str] = Field(default_factory=list)
    chunks: int = 0
    entities: int = 0
    refs: int = 0
    unresolved_refs: int = 0


def ingest_corpus(corpus_dir: Path, store: SqliteStore) -> IngestReport:
    paths = sorted(corpus_dir.glob("*.md"))
    parsed = [(p, p.read_text(encoding="utf-8")) for p in paths]
    docs = [parse_markdown(raw) for _, raw in parsed]
    known_ids = {req.id for doc in docs for req in doc.requirements}

    report = IngestReport()
    for (path, raw), doc in zip(parsed, docs, strict=True):
        doc_hash = content_hash(raw)
        if store.document_hash(doc.id) == doc_hash:
            report.unchanged_docs.append(doc.id)
            continue

        is_update = store.document_hash(doc.id) is not None
        store.replace_document(
            doc_id=doc.id,
            content_hash=doc_hash,
            source_path=str(path),
            chunks=chunk_document(doc),
            entities=extract_entities(doc),
            refs=extract_refs(doc, known_ids),
        )
        (report.updated_docs if is_update else report.new_docs).append(doc.id)

    report.chunks = store.chunk_count()
    report.entities = store.entity_count()
    report.refs = store.ref_count()
    report.unresolved_refs = store.unresolved_ref_count()
    return report
