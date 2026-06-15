"""Structure-aware chunking.

Each requirement becomes one chunk that keeps its requirement ID, section path,
parameters, and status. Requirements are already atomic, self-contained units, so
splitting them would only break citations — the chunk boundary is the requirement.
"""

from __future__ import annotations

import hashlib

from requirements_audit.models import Chunk, RequirementDocument


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_document(doc: RequirementDocument) -> list[Chunk]:
    chunks: list[Chunk] = []
    for req in doc.requirements:
        chunks.append(
            Chunk(
                id=req.id,
                doc_id=doc.id,
                requirement_id=req.id,
                section_path=[doc.title, req.section],
                title=req.title,
                text=req.text,
                content_hash=content_hash(req.text),
                parameters=req.parameters,
                status=req.status,
            )
        )
    return chunks
