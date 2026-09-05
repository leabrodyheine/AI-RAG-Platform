import math

from retrieval_service.corpus import EVALUATION_DOCUMENTS
from retrieval_service.embeddings import (
    EMBEDDING_DIMENSIONS,
    FeatureHashEmbeddingProvider,
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
