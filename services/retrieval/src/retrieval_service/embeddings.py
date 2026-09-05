"""Small deterministic embeddings for exercising the local vector pipeline."""

import hashlib
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

EMBEDDING_DIMENSIONS = 256
SEMANTIC_EMBEDDING_DIMENSIONS = 384
DEFAULT_SEMANTIC_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_SEMANTIC_MODEL_VERSION = "fastembed:BAAI/bge-small-en-v1.5:v1"
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def default_semantic_model_version(model_name: str) -> str:
    return f"fastembed:{model_name}:v1"


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


class FastEmbedProvider:
    dimensions = SEMANTIC_EMBEDDING_DIMENSIONS

    def __init__(
        self,
        model_name: str = DEFAULT_SEMANTIC_MODEL,
        version: str = DEFAULT_SEMANTIC_MODEL_VERSION,
        cache_dir: str | None = None,
        *,
        model: Any | None = None,
    ) -> None:
        if model is None:
            from fastembed import TextEmbedding

            model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self._model = model
        self.model_name = model_name
        self.version = version

    def embed_query(self, text: str) -> tuple[float, ...]:
        return self._collect_vectors(self._model.query_embed(text), expected_count=1)[0]

    def embed_passages(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        return self._collect_vectors(
            self._model.passage_embed(texts),
            expected_count=len(texts),
        )

    def _collect_vectors(
        self,
        vectors: Iterable[Any],
        *,
        expected_count: int,
    ) -> list[tuple[float, ...]]:
        collected = [tuple(float(value) for value in vector) for vector in vectors]
        if len(collected) != expected_count:
            raise RuntimeError(
                f"embedding model returned {len(collected)} vectors; expected {expected_count}"
            )
        if any(len(vector) != self.dimensions for vector in collected):
            raise RuntimeError(
                f"embedding model must return {self.dimensions}-dimensional vectors"
            )
        return collected


def create_embedding_provider(
    provider_name: str,
    *,
    model_name: str = DEFAULT_SEMANTIC_MODEL,
    model_version: str = DEFAULT_SEMANTIC_MODEL_VERSION,
    cache_dir: str | None = None,
) -> EmbeddingProvider:
    if provider_name == "feature-hash":
        return FeatureHashEmbeddingProvider()
    if provider_name == "fastembed":
        return FastEmbedProvider(
            model_name=model_name,
            version=model_version,
            cache_dir=cache_dir,
        )
    raise ValueError(f"unsupported embedding provider: {provider_name}")


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
