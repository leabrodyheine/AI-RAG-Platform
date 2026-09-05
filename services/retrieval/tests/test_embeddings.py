import math
import os

import pytest
from retrieval_service.corpus import EVALUATION_DOCUMENTS
from retrieval_service.embeddings import (
    DEFAULT_SEMANTIC_MODEL,
    DEFAULT_SEMANTIC_MODEL_VERSION,
    EMBEDDING_DIMENSIONS,
    SEMANTIC_EMBEDDING_DIMENSIONS,
    FastEmbedProvider,
    FeatureHashEmbeddingProvider,
    create_embedding_provider,
    embed_text,
)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )


def test_embeddings_are_fixed_size_deterministic_and_normalized() -> None:
    first = embed_text("Retrieval latency improved with caching.")
    second = embed_text("Retrieval latency improved with caching.")

    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0)


def test_embeddings_rank_shared_terms_above_unrelated_text() -> None:
    query = embed_text("retrieval latency")
    related = embed_text("retrieval cache latency results")
    unrelated = embed_text("citation correctness evaluation")

    assert cosine_similarity(query, related) > cosine_similarity(query, unrelated)


def test_empty_text_has_a_zero_vector() -> None:
    assert embed_text("   ") == (0.0,) * EMBEDDING_DIMENSIONS


def test_unrelated_query_does_not_collide_with_evaluation_corpus() -> None:
    query = embed_text("weather forecast")

    similarities = [
        cosine_similarity(
            query,
            embed_text("\n".join((document.title, " ".join(document.tags), document.content))),
        )
        for document in EVALUATION_DOCUMENTS
    ]

    assert max(similarities) == 0


def test_feature_hash_provider_embeds_queries_and_passages() -> None:
    provider = FeatureHashEmbeddingProvider()

    assert provider.version == "feature-hash-v1"
    assert provider.dimensions == EMBEDDING_DIMENSIONS
    assert provider.embed_query("retrieval latency") == embed_text("retrieval latency")
    assert provider.embed_passages(["first", "second"]) == [
        embed_text("first"),
        embed_text("second"),
    ]


class FakeSemanticModel:
    def query_embed(self, _text: str):
        yield [0.25] * SEMANTIC_EMBEDDING_DIMENSIONS

    def passage_embed(self, texts):
        for index, _text in enumerate(texts, start=1):
            yield [float(index)] * SEMANTIC_EMBEDDING_DIMENSIONS


def test_fastembed_provider_uses_query_and_passage_encoders() -> None:
    provider = FastEmbedProvider(model=FakeSemanticModel())

    assert provider.model_name == DEFAULT_SEMANTIC_MODEL
    assert provider.version == DEFAULT_SEMANTIC_MODEL_VERSION
    assert provider.embed_query("latency") == (0.25,) * SEMANTIC_EMBEDDING_DIMENSIONS
    assert provider.embed_passages(["first", "second"]) == [
        (1.0,) * SEMANTIC_EMBEDDING_DIMENSIONS,
        (2.0,) * SEMANTIC_EMBEDDING_DIMENSIONS,
    ]


def test_fastembed_provider_disables_onnx_telemetry_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ORT_DISABLE_TELEMETRY", raising=False)

    FastEmbedProvider(model=FakeSemanticModel())

    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"


def test_fastembed_provider_does_not_call_model_for_an_empty_batch() -> None:
    provider = FastEmbedProvider(model=FakeSemanticModel())

    assert provider.embed_passages([]) == []


def test_fastembed_provider_rejects_the_wrong_vector_dimensions() -> None:
    class WrongDimensions(FakeSemanticModel):
        def query_embed(self, _text: str):
            yield [0.25] * 12

    provider = FastEmbedProvider(model=WrongDimensions())

    with pytest.raises(RuntimeError, match="384-dimensional"):
        provider.embed_query("latency")


def test_provider_factory_builds_the_offline_provider() -> None:
    provider = create_embedding_provider("feature-hash")

    assert isinstance(provider, FeatureHashEmbeddingProvider)


def test_provider_factory_rejects_unknown_providers() -> None:
    with pytest.raises(ValueError, match="unsupported embedding provider"):
        create_embedding_provider("unknown")
