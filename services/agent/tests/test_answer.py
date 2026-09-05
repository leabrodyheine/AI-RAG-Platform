from dataclasses import dataclass, field

import pytest
from agent_service.clients.retrieval import RetrievalClientError, RetrievalTimeoutError
from agent_service.dependencies import get_retrieval_client
from agent_service.main import app
from agent_service.schemas import Citation
from fastapi.testclient import TestClient

client = TestClient(app)


def retrieved_evidence() -> list[Citation]:
    return [
        Citation(
            id="retrieval-benchmark-1842",
            title="Retrieval benchmark · run #1842",
            source="evaluation/performance/retrieval.json",
            excerpt="Cache misses increased vector-search p95 from 112 ms to 391 ms.",
            relevance=0.9,
        )
    ]


@dataclass
class StubRetrievalClient:
    results: list[Citation] = field(default_factory=retrieved_evidence)
    error: Exception | None = None
    calls: list[tuple[str, int, str | None]] = field(default_factory=list)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        request_id: str | None = None,
    ) -> list[Citation]:
        self.calls.append((query, top_k, request_id))
        if self.error:
            raise self.error
        return self.results


@pytest.fixture
def retrieval_client() -> StubRetrievalClient:
    return StubRetrievalClient()


@pytest.fixture(autouse=True)
def override_retrieval_client(retrieval_client: StubRetrievalClient):
    app.dependency_overrides[get_retrieval_client] = lambda: retrieval_client
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_answer_returns_a_grounded_contract_response(
    retrieval_client: StubRetrievalClient,
) -> None:
    response = client.post(
        "/answer",
        json={"question": "What is driving p95 latency?"},
        headers={"X-Request-ID": "agent-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "agent-request-123"
    body = response.json()
    assert set(body) == {"content", "citations", "trace", "totalDurationMs"}
    assert "strongest evidence for this performance investigation" in body["content"]
    assert body["citations"] == [
        {
            "id": "retrieval-benchmark-1842",
            "title": "Retrieval benchmark · run #1842",
            "source": "evaluation/performance/retrieval.json",
            "excerpt": "Cache misses increased vector-search p95 from 112 ms to 391 ms.",
            "relevance": 0.9,
        }
    ]
    assert [step["label"] for step in body["trace"]] == ["Retrieve", "Synthesize"]
    assert body["trace"][0]["detail"] == "1 matching evaluation source"
    assert body["trace"][1]["detail"] == (
        "Performance answer grounded in 1 retrieved source"
    )
    assert body["totalDurationMs"] >= 0
    assert retrieval_client.calls == [
        ("What is driving p95 latency?", 3, "agent-request-123")
    ]


@pytest.mark.parametrize(
    ("question", "expected_category"),
    [
        ("Why is model performance slow?", "performance"),
        ("Compare retrieval cache behavior", "retrieval"),
        ("Summarize the latest run", "general"),
    ],
)
def test_answer_classifies_grounded_questions(
    question: str,
    expected_category: str,
) -> None:
    response = client.post("/answer", json={"question": question})

    assert response.status_code == 200
    assert f"strongest evidence for this {expected_category} investigation" in response.json()[
        "content"
    ]
    assert response.json()["trace"][1]["detail"].startswith(expected_category.capitalize())


def test_answer_reports_when_retrieval_finds_no_evidence(
    retrieval_client: StubRetrievalClient,
) -> None:
    retrieval_client.results = []

    response = client.post("/answer", json={"question": "weather forecast"})

    assert response.status_code == 200
    assert response.json()["citations"] == []
    assert response.json()["content"].startswith("No matching evaluation evidence was found")
    assert response.json()["trace"][0]["detail"] == "0 matching evaluation sources"


def test_answer_strips_surrounding_question_whitespace(
    retrieval_client: StubRetrievalClient,
) -> None:
    response = client.post("/answer", json={"question": "  CACHE behavior\n"})

    assert response.status_code == 200
    assert retrieval_client.calls[0][0] == "CACHE behavior"


@pytest.mark.parametrize("question", ["", "   \n\t"])
def test_answer_rejects_empty_questions(
    question: str,
    retrieval_client: StubRetrievalClient,
) -> None:
    response = client.post("/answer", json={"question": question})

    assert response.status_code == 422
    assert retrieval_client.calls == []


def test_answer_accepts_the_question_length_limit() -> None:
    response = client.post("/answer", json={"question": "a" * 4000})

    assert response.status_code == 200


def test_answer_rejects_questions_over_the_length_limit(
    retrieval_client: StubRetrievalClient,
) -> None:
    response = client.post("/answer", json={"question": "a" * 4001})

    assert response.status_code == 422
    assert retrieval_client.calls == []


def test_answer_rejects_unknown_request_fields(
    retrieval_client: StubRetrievalClient,
) -> None:
    response = client.post(
        "/answer",
        json={"question": "Summarize the run", "unexpected": True},
    )

    assert response.status_code == 422
    assert retrieval_client.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            RetrievalClientError("private connection detail"),
            503,
            "The retrieval service is temporarily unavailable.",
        ),
        (
            RetrievalTimeoutError("private timeout detail"),
            504,
            "The retrieval service did not respond in time.",
        ),
    ],
)
def test_answer_translates_retrieval_failures(
    retrieval_client: StubRetrievalClient,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    retrieval_client.error = error

    response = client.post(
        "/answer",
        json={"question": "What is slow?"},
        headers={"X-Request-ID": "agent-error-123"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert response.headers["X-Request-ID"] == "agent-error-123"
    assert str(error) not in response.text
