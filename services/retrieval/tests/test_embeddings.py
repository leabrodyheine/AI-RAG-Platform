import math

from retrieval_service.embeddings import EMBEDDING_DIMENSIONS, embed_text


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
