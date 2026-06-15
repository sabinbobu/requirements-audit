"""Analyst agent (Q&A): answers a question with inline, source-grounded citations.

The agent has exactly the three Retriever tools and a typed `Answer` output. It is
instructed to ground every claim in a retrieved requirement and to return an empty
`citations` list when the corpus does not contain the answer — the honest
no-result / missing-data behaviour the golden set scores.
"""

from __future__ import annotations

from pydantic_ai import Agent, RunContext

from requirements_audit.models import Answer, Chunk
from requirements_audit.retrieval.lexical import ScoredChunk
from requirements_audit.tools import retriever
from requirements_audit.tools.retriever import ResolvedRef, RetrievalDeps

INSTRUCTIONS = """\
You answer questions about a corpus of engineering requirement documents.

Use `hybrid_search` to find relevant requirements; use `get_section` to read a
document section and `find_refs` to follow a requirement's references. Base every
statement only on retrieved requirement text — never invent values.

Return an `Answer` whose `text` is concise and whose `citations` list contains one
entry per requirement you relied on, each with the exact `doc_id`, `requirement_id`,
and a verbatim `quote` from that requirement. If the corpus does not contain the
answer, say so plainly and return an empty `citations` list.
"""

analyst_agent = Agent(
    deps_type=RetrievalDeps,
    output_type=Answer,
    instructions=INSTRUCTIONS,
    name="analyst",
)


@analyst_agent.tool
def hybrid_search(ctx: RunContext[RetrievalDeps], query: str, k: int = 5) -> list[ScoredChunk]:
    """Rank requirements by lexical relevance to the query; returns the top k."""
    return retriever.hybrid_search(ctx.deps, query, k)


@analyst_agent.tool
def get_section(ctx: RunContext[RetrievalDeps], doc_id: str, section: str) -> list[Chunk]:
    """Return every requirement in the named section of a document."""
    return retriever.get_section(ctx.deps, doc_id, section)


@analyst_agent.tool
def find_refs(ctx: RunContext[RetrievalDeps], req_id: str) -> list[ResolvedRef]:
    """Return the requirements that req_id references, annotated with target status."""
    return retriever.find_refs(ctx.deps, req_id)
