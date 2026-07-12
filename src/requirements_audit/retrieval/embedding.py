"""Embedders for the dense retrieval arm — pluggable, honestly labeled.

Two implementations, mirroring the project's two-tier eval philosophy:

- `HashingEmbedder` — deterministic feature hashing over word tokens and
  character trigrams. No model download, no API key, bit-identical vectors on
  every machine, so the dense/hybrid benchmark *wiring* runs in the keyless CI
  gate. It captures token overlap (BM25-like, with subword fuzziness), not
  meaning — its numbers are a wiring floor, not a semantic-embedding claim.
- `OpenAIEmbedder` — the pinned `Settings.embedding_model`
  (text-embedding-3-small); used in live/nightly runs when an OpenAI key is
  present to produce the real dense numbers.

Every benchmark row records which embedder produced it (`Embedder.name`), so a
hash-embedder run can never masquerade as a semantic one in the README table.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from enum import StrEnum
from hashlib import blake2b
from typing import Protocol, runtime_checkable

from requirements_audit.config import Settings
from requirements_audit.llm.provider import MissingCredentialsError

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    """Anything that turns texts into fixed-dimension vectors.

    `name` is embedded into benchmark notes so reports disclose their backend.
    """

    name: str
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbedderChoice(StrEnum):
    """CLI-facing embedder selection. AUTO prefers OpenAI when a key is set."""

    AUTO = "auto"
    HASH = "hash"
    OPENAI = "openai"


def _features(text: str) -> list[str]:
    """Hashing features: word tokens plus character trigrams of longer tokens.

    Trigrams give partial-match fuzziness (`watchdog_timeout` still overlaps a
    query saying `watchdog timer`) that plain token hashing would miss.
    """
    tokens = _TOKEN.findall(text.lower())
    feats = list(tokens)
    for tok in tokens:
        if len(tok) > 3:
            feats.extend(tok[i : i + 3] for i in range(len(tok) - 2))
    return feats


class HashingEmbedder:
    """Deterministic feature-hashing embedder (the "hashing trick").

    Each feature is hashed (blake2b — stable across processes, unlike Python's
    randomized `hash()`) to a bucket and a sign; occurrences accumulate; the
    vector is L2-normalized so Qdrant's cosine distance behaves.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for feat in _features(text):
            digest = blake2b(feat.encode("utf-8"), digest_size=8).digest()
            # First 4 bytes pick the bucket, byte 5 picks the sign — both are
            # pure functions of the feature string, hence deterministic.
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec  # featureless text (e.g. punctuation-only) → zero vector
        return [v / norm for v in vec]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]


class OpenAIEmbedder:
    """OpenAI embeddings with the model version pinned in `Settings`.

    Batches inputs to stay well under the API's per-request item limit. Only
    constructed when a key is available (see `build_embedder`).
    """

    _BATCH = 100
    # Output dimension of text-embedding-3-small; the API also accepts a
    # `dimensions` override, which we deliberately do not use — pin everything.
    _DIM = 1536

    def __init__(self, api_key: str, model: str) -> None:
        # Local import keeps `import requirements_audit.retrieval.embedding`
        # cheap for the keyless paths that never touch OpenAI.
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.dim = self._DIM
        self.name = f"openai:{model}"

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH):
            batch = list(texts[start : start + self._BATCH])
            response = self._client.embeddings.create(model=self._model, input=batch)
            # The API returns items in input order; keep it explicit anyway.
            out.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        return out


def build_embedder(settings: Settings, choice: EmbedderChoice = EmbedderChoice.AUTO) -> Embedder:
    """Resolve the embedder for a run.

    AUTO uses OpenAI when a key is configured (live/nightly) and falls back to
    the hashing embedder otherwise (keyless CI) — same key-presence switch the
    rest of the eval harness uses.
    """
    if choice is EmbedderChoice.HASH:
        return HashingEmbedder()
    if choice is EmbedderChoice.OPENAI and not settings.openai_api_key:
        raise MissingCredentialsError(
            "OPENAI_API_KEY is required for --embedder openai; "
            "use --embedder hash for the deterministic keyless run."
        )
    if settings.openai_api_key and choice in (EmbedderChoice.AUTO, EmbedderChoice.OPENAI):
        return OpenAIEmbedder(api_key=settings.openai_api_key, model=settings.embedding_model)
    return HashingEmbedder()
