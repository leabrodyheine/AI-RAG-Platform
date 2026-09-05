from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from retrieval_service.corpus import EvaluationDocument
from retrieval_service.dependencies import get_document_store
from retrieval_service.main import app
from retrieval_service.search import RankedDocument

client = TestClient(app)


def test_search_ranks_matching_evaluation_evidence() -> None:
    response = client.post(
        "/search",
        json={"query": "What is driving p95 retrieval latency?", "topK": 2},
        headers={"X-Request-ID": "retrieval-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "retrieval-request-123"
    results = response.json()["results"]
    assert len(results) == 2
    assert results[0]["id"] == "retrieval-benchmark-1842"
    assert set(results[0]) == {"id", "title", "source", "excerpt", "relevance"}
    assert 0 < results[0]["relevance"] <= 1


def test_search_obeys_top_k_and_uses_stable_ranking() -> None:
    response = client.post(
        "/search",
        json={"query": "retrieval cache latency", "topK": 1},
    )

    assert response.status_code == 200
    assert [result["id"] for result in response.json()["results"]] == [
        "cache-comparison-1842"
    ]
    UUID(response.headers["X-Request-ID"])


def test_search_returns_no_evidence_for_an_unmatched_query() -> None:
    response = client.post("/search", json={"query": "weather forecast"})

    assert response.status_code == 200
    assert response.json() == {"results": []}


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   \n"},
        {"query": "valid", "topK": 0},
        {"query": "valid", "topK": 11},
        {"query": "valid", "unexpected": True},
    ],
)
def test_search_rejects_invalid_requests(payload: dict[str, object]) -> None:
    response = client.post("/search", json=payload)

    assert response.status_code == 422


def test_search_accepts_the_query_length_limit() -> None:
    response = client.post("/search", json={"query": "a" * 4000})

    assert response.status_code == 200


def test_search_rejects_queries_over_the_length_limit() -> None:
    response = client.post("/search", json={"query": "a" * 4001})

    assert response.status_code == 422


def test_search_ranks_documents_loaded_from_persistent_storage() -> None:
    stored_result = RankedDocument(
        document=EvaluationDocument(
            id="stored-result",
            title="Stored throughput result",
            source="evaluation/stored.json",
            content="The matching stored chunk reached 27 requests per second.",
            tags=("throughput",),
        ),
        relevance=0.91,
    )

    class StoredDocuments:
        def __init__(self) -> None:
            self.search_request = None

        async def search(self, query: str, top_k: int):
            self.search_request = (query, top_k)
            return [stored_result]

    store = StoredDocuments()
    app.dependency_overrides[get_document_store] = lambda: store
    try:
        response = client.post(
            "/search", json={"query": "stored throughput", "topK": 2}
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert store.search_request == ("stored throughput", 2)
    assert response.json()["results"] == [
        {
            "id": "stored-result",
            "title": "Stored throughput result",
            "source": "evaluation/stored.json",
            "excerpt": "The matching stored chunk reached 27 requests per second.",
            "relevance": 0.91,
        }
    ]


def test_persistent_search_does_not_fall_back_when_vectors_have_no_match() -> None:
    class NoVectorMatch:
        async def search(self, _query: str, _top_k: int):
            return []

    app.dependency_overrides[get_document_store] = lambda: NoVectorMatch()
    try:
        response = client.post("/search", json={"query": "retrieval latency"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"results": []}
