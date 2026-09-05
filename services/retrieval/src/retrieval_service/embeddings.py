"""Small deterministic embeddings for exercising the local vector pipeline."""

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

EMBEDDING_DIMENSIONS = 256
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(Protocol):
    dimensions: int
    version: str

    def embed_query(self, text: str) -> tuple[float, ...]: ...

    def embed_passages(self, texts: Sequence[str]) -> list[tuple[float, ...]]: ...


class FeatureHashEmbeddingProvider:
    dimensions = EMBEDDING_DIMENSIONS
    version = "feature-hash-v1"

    def embed_query(self, text: str) -> tuple[float, ...]:
        return embed_text(text)

    def embed_passages(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        return [embed_text(text) for text in texts]


def embed_text(text: str) -> tuple[float, ...]:
    """Create a normalized feature-hashed vector without external model downloads."""
    tokens = TOKEN_PATTERN.findall(text.casefold())
    features = tokens + [
        f"{left}:{right}" for left, right in zip(tokens, tokens[1:], strict=False)
    ]
    vector = [0.0] * EMBEDDING_DIMENSIONS

    for feature in features:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        bucket = int.from_bytes(digest) % EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[0] & 1 else -1.0
        vector[bucket] += sign

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return tuple(vector)
    return tuple(value / magnitude for value in vector)
