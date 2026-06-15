"""Ingestion: parse requirement documents, chunk them, extract entities and
references, and store the result in SQLite with a content-hash ledger.

The pipeline is deterministic and offline. Embedding into the Qdrant hybrid index
is a separate step layered on top (it needs a running Qdrant and an embedding
provider) and is added in a later branch.
"""

from __future__ import annotations
