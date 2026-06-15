"""SQLite store: chunks, entities, cross-references, and a content-hash ledger.

The ledger records a content hash per document so re-ingesting an unchanged corpus
does no work. When a document's hash changes, its rows are replaced atomically.
This is the canonical text/metadata store; the Qdrant vector index is layered on
top later for similarity search.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from requirements_audit.models import (
    Chunk,
    CrossRef,
    Entity,
    EntityType,
    RequirementStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger (
    doc_id        TEXT PRIMARY KEY,
    content_hash  TEXT NOT NULL,
    source_path   TEXT,
    chunk_count   INTEGER NOT NULL,
    ingested_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id            TEXT PRIMARY KEY,
    doc_id        TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    section_path  TEXT NOT NULL,
    title         TEXT NOT NULL,
    text          TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    parameters    TEXT NOT NULL,
    status        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entities (
    name          TEXT NOT NULL,
    entity_type   TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    doc_id        TEXT NOT NULL,
    value         TEXT
);
CREATE TABLE IF NOT EXISTS refs (
    doc_id        TEXT NOT NULL,
    from_req      TEXT NOT NULL,
    to_req        TEXT NOT NULL,
    resolved      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_entities_doc ON entities(doc_id);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
"""


class SqliteStore:
    """A thin typed wrapper over a SQLite database. Use as a context manager."""

    def __init__(self, path: Path | str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> SqliteStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ─── ledger ───────────────────────────────────────────────────────────────
    def document_hash(self, doc_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT content_hash FROM ledger WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return None if row is None else str(row["content_hash"])

    def replace_document(
        self,
        doc_id: str,
        content_hash: str,
        source_path: str,
        chunks: list[Chunk],
        entities: list[Entity],
        refs: list[CrossRef],
    ) -> None:
        """Atomically replace all stored rows for one document."""
        with self._conn:  # transaction
            self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self._conn.execute("DELETE FROM entities WHERE doc_id = ?", (doc_id,))
            self._conn.execute("DELETE FROM refs WHERE doc_id = ?", (doc_id,))
            self._conn.executemany(
                "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)",
                [
                    (
                        c.id,
                        c.doc_id,
                        c.requirement_id,
                        json.dumps(c.section_path),
                        c.title,
                        c.text,
                        c.content_hash,
                        json.dumps(c.parameters),
                        c.status.value,
                    )
                    for c in chunks
                ],
            )
            self._conn.executemany(
                "INSERT INTO entities VALUES (?,?,?,?,?)",
                [
                    (e.name, e.entity_type.value, e.requirement_id, e.doc_id, e.value)
                    for e in entities
                ],
            )
            self._conn.executemany(
                "INSERT INTO refs VALUES (?,?,?,?)",
                [(doc_id, r.from_req, r.to_req, int(r.resolved)) for r in refs],
            )
            self._conn.execute(
                "INSERT INTO ledger VALUES (?,?,?,?,?) "
                "ON CONFLICT(doc_id) DO UPDATE SET "
                "content_hash=excluded.content_hash, source_path=excluded.source_path, "
                "chunk_count=excluded.chunk_count, ingested_at=excluded.ingested_at",
                (
                    doc_id,
                    content_hash,
                    source_path,
                    len(chunks),
                    datetime.now(UTC).isoformat(),
                ),
            )

    # ─── queries ────────────────────────────────────────────────────────────────
    def chunk_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def entity_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])

    def ref_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0])

    def unresolved_ref_count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM refs WHERE resolved = 0").fetchone()[0])

    def all_chunks(self) -> list[Chunk]:
        rows = self._conn.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        return [
            Chunk(
                id=row["id"],
                doc_id=row["doc_id"],
                requirement_id=row["requirement_id"],
                section_path=json.loads(row["section_path"]),
                title=row["title"],
                text=row["text"],
                content_hash=row["content_hash"],
                parameters=json.loads(row["parameters"]),
                status=RequirementStatus(row["status"]),
            )
            for row in rows
        ]

    def entities_for_requirement(self, requirement_id: str) -> list[Entity]:
        rows = self._conn.execute(
            "SELECT * FROM entities WHERE requirement_id = ?", (requirement_id,)
        ).fetchall()
        return [
            Entity(
                name=row["name"],
                entity_type=EntityType(row["entity_type"]),
                requirement_id=row["requirement_id"],
                doc_id=row["doc_id"],
                value=row["value"],
            )
            for row in rows
        ]
