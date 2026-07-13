"""Ingestion pipeline: parse -> chunk -> extract -> store, with idempotent re-runs.

A document is re-processed only when its content hash changed since the last run,
so re-ingesting an unchanged corpus reports everything as unchanged and writes
nothing. The returned report carries both the store-wide totals and the per-run
ledger delta (new / updated / unchanged documents).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field

from requirements_audit.ingestion.chunker import chunk_document
from requirements_audit.ingestion.extract import extract_entities, extract_refs
from requirements_audit.ingestion.parser import corpus_paths, parse_file
from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Requirement, RequirementDocument


class IngestReport(BaseModel):
    new_docs: list[str] = Field(default_factory=list)
    updated_docs: list[str] = Field(default_factory=list)
    unchanged_docs: list[str] = Field(default_factory=list)
    chunks: int = 0
    entities: int = 0
    refs: int = 0
    unresolved_refs: int = 0


def ingest_corpus(corpus_dir: Path, store: SqliteStore) -> IngestReport:
    paths = corpus_paths(corpus_dir)  # *.md and *.pdf, ordered by filename
    docs = [parse_file(p) for p in paths]
    known_ids = {req.id for doc in docs for req in doc.requirements}

    report = IngestReport()
    for path, doc in zip(paths, docs, strict=True):
        # Hash the raw bytes: works for both formats, and a re-exported PDF
        # re-ingests only when its bytes actually changed.
        doc_hash = hashlib.sha256(path.read_bytes()).hexdigest()
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


def reconstruct_document(store: SqliteStore, doc_id: str) -> RequirementDocument | None:
    """Best-effort reconstruction of a document from its stored chunks — the
    write path behind the "corrected copy" convenience artifact written after
    a requirement is edited through the UI. `None` if the document is unknown.

    `superseded_by` isn't persisted anywhere in the store (only a target's own
    `status` matters for `detect_superseded_references`), so a reconstructed
    superseded requirement omits that field — it never reaches re-audit, which
    reads the store directly, not this reconstruction.
    """
    chunks = store.chunks_for_doc(doc_id)
    if not chunks:
        return None
    requirements = [
        Requirement(
            id=c.requirement_id,
            doc_id=c.doc_id,
            section=c.section_path[-1] if c.section_path else "",
            title=c.title,
            text=c.text,
            category="",
            parameters=c.parameters,
            refs=[r.to_req for r in store.refs_from(c.requirement_id)],
            status=c.status,
        )
        for c in chunks
    ]
    return RequirementDocument(
        id=doc_id, title=doc_id, doc_type="corrected", requirements=requirements
    )
