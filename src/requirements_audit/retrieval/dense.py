"""Dense retrieval: cosine similarity over an in-process Qdrant collection.

This is the *dense arm* of hybrid retrieval. The Qdrant client runs in local
(":memory:") mode — the same engine and API as the docker-compose service, but
in-process, so benchmarks and CI need no running container. Persisting vectors
at ingest time against the served Qdrant is Phase F (ops) work; for benchmarking
we embed the (small) corpus on the fly.
"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from requirements_audit.ingestion.store import SqliteStore
from requirements_audit.models import Chunk
from requirements_audit.retrieval.embedding import Embedder
from requirements_audit.retrieval.lexical import ScoredChunk


def _chunk_text(chunk: Chunk) -> str:
    """The text a chunk is embedded from: title, body, and parameter pairs.

    Mirrors the term sources of `lexical._chunk_terms` so the two arms rank
    over the same information and their benchmark numbers are comparable.
    """
    params = " ".join(f"{k} {v}" for k, v in chunk.parameters.items())
    return f"{chunk.title}\n{chunk.text}\n{params}"


class DenseIndex:
    """An in-memory Qdrant vector index. Build once, query many times."""

    _COLLECTION = "chunks"

    def __init__(self, chunks: list[Chunk], embedder: Embedder) -> None:
        self._chunks = chunks
        self._embedder = embedder
        self._client = QdrantClient(location=":memory:")
        self._client.create_collection(
            collection_name=self._COLLECTION,
            vectors_config=VectorParams(size=embedder.dim, distance=Distance.COSINE),
        )
        if chunks:
            vectors = embedder.embed([_chunk_text(c) for c in chunks])
            # Point id == position in self._chunks, so a hit maps straight back
            # to its Chunk without a payload round-trip.
            self._client.upsert(
                collection_name=self._COLLECTION,
                points=[
                    PointStruct(id=i, vector=vectors[i], payload={"req": c.requirement_id})
                    for i, c in enumerate(chunks)
                ],
            )

    @classmethod
    def from_store(cls, store: SqliteStore, embedder: Embedder) -> DenseIndex:
        return cls(store.all_chunks(), embedder)

    def search(self, query: str, k: int = 5) -> list[ScoredChunk]:
        if not self._chunks:
            return []
        [query_vector] = self._embedder.embed([query])
        if not any(query_vector):
            # A featureless query embeds to the zero vector; cosine against it
            # is undefined, so return nothing rather than noise.
            return []
        hits = self._client.query_points(
            collection_name=self._COLLECTION, query=query_vector, limit=k
        ).points
        scored = [
            ScoredChunk(chunk=self._chunks[int(hit.id)], score=float(hit.score))
            for hit in hits
            if hit.score > 0.0  # drop anti-correlated matches, mirroring lexical
        ]
        # Stable: score desc, then requirement id asc for determinism.
        scored.sort(key=lambda s: (-s.score, s.chunk.requirement_id))
        return scored
