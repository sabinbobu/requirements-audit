"""The Retriever: three typed, deterministic tools the agents call.

These are plain functions over the store + lexical index — no LLM, no hidden
state — so they are trivially unit-testable and the Analyst's tool calls have a
fixed, assertable shape (Level-1 eval: tool-call shape). They are registered onto
the PydanticAI Analyst agent via thin `RunContext` wrappers in `agents.analyst`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk, RequirementStatus
from requirements_audit.retrieval.lexical import LexicalIndex, ScoredChunk


@dataclass
class RetrievalDeps:
    """Shared dependencies for the retrieval tools (and the Analyst agent)."""

    store: SqliteStore
    index: LexicalIndex

    @classmethod
    def from_store(cls, store: SqliteStore) -> RetrievalDeps:
        return cls(store=store, index=LexicalIndex.from_store(store))


class ResolvedRef(BaseModel):
    """An outgoing cross-reference annotated with the target's current status.

    `to_status` is None when the target requirement is absent from the corpus
    (a dangling reference); `superseded` is the signal the audit path keys on.
    """

    from_req: str
    to_req: str
    resolved: bool
    to_status: RequirementStatus | None


def hybrid_search(deps: RetrievalDeps, query: str, k: int = 5) -> list[ScoredChunk]:
    """Rank requirements by lexical relevance to `query` (BM25). Top `k`."""
    return deps.index.search(query, k)


def get_section(deps: RetrievalDeps, doc_id: str, section: str) -> list[Chunk]:
    """Every requirement chunk in a document's named section."""
    return deps.store.get_section(doc_id, section)


def find_refs(deps: RetrievalDeps, req_id: str) -> list[ResolvedRef]:
    """The cross-references a requirement makes, each annotated with the target's status."""
    refs = deps.store.refs_from(req_id)
    out: list[ResolvedRef] = []
    for ref in refs:
        target = deps.store.chunk(ref.to_req) if ref.resolved else None
        out.append(
            ResolvedRef(
                from_req=ref.from_req,
                to_req=ref.to_req,
                resolved=ref.resolved,
                to_status=target.status if target is not None else None,
            )
        )
    return out
