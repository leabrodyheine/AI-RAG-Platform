from dataclasses import dataclass, field

import pytest
from agent_service.clients.inference import (
    GeneratedAnswer,
    InferenceClientError,
    InferenceResponseError,
    InferenceTimeoutError,
)
from agent_service.clients.retrieval import RetrievalClientError, RetrievalTimeoutError
from agent_service.dependencies import get_inference_client, get_retrieval_client
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


@dataclass
class StubInferenceClient:
    answer: GeneratedAnswer = field(
        default_factory=lambda: GeneratedAnswer(
            content="Based on the retrieved evidence, cache misses raised p95. [1]",
            model="deterministic-grounded-v1",
            prompt_tokens=64,
            completion_tokens=9,
        )
    )
    error: Exception | None = None
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        request_id: str | None = None,
    ) -> GeneratedAnswer:
        self.calls.append((prompt, request_id))
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def retrieval_client() -> StubRetrievalClient:
    return StubRetrievalClient()


@pytest.fixture
def inference_client() -> StubInferenceClient:
    return StubInferenceClient()


@pytest.fixture(autouse=True)
def override_clients(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
):
    app.dependency_overrides[get_retrieval_client] = lambda: retrieval_client
    app.dependency_overrides[get_inference_client] = lambda: inference_client
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_answer_returns_the_generated_contract_response(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
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
    assert body["content"] == (
        "Based on the retrieved evidence, cache misses raised p95. [1]"
    )
    assert body["citations"] == [
        {
            "id": "retrieval-benchmark-1842",
            "title": "Retrieval benchmark · run #1842",
            "source": "evaluation/performance/retrieval.json",
            "excerpt": "Cache misses increased vector-search p95 from 112 ms to 391 ms.",
            "relevance": 0.9,
        }
    ]
    assert [step["label"] for step in body["trace"]] == ["Retrieve", "Generate"]
    assert body["trace"][0]["detail"] == "1 matching evaluation source"
    assert body["trace"][1]["detail"] == (
        "deterministic-grounded-v1 produced 9 completion tokens from 64 prompt tokens"
    )
    assert body["totalDurationMs"] >= 0
    assert retrieval_client.calls == [
        ("What is driving p95 latency?", 3, "agent-request-123")
    ]


def test_answer_sends_a_grounded_prompt_to_inference(
    inference_client: StubInferenceClient,
) -> None:
    response = client.post(
        "/answer",
        json={"question": "What is driving p95 latency?"},
        headers={"X-Request-ID": "agent-request-123"},
    )

    assert response.status_code == 200
    prompt, forwarded_request_id = inference_client.calls[0]
    assert forwarded_request_id == "agent-request-123"
    assert "Question: What is driving p95 latency?" in prompt
    assert (
        "[1] Retrieval benchmark · run #1842 — "
        "Cache misses increased vector-search p95 from 112 ms to 391 ms."
    ) in prompt


def test_answer_generates_over_an_empty_evidence_set(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    retrieval_client.results = []
    inference_client.answer = GeneratedAnswer(
        content="The retrieved evidence does not support an answer to this question.",
        model="deterministic-grounded-v1",
        prompt_tokens=20,
        completion_tokens=11,
    )

    response = client.post("/answer", json={"question": "weather forecast"})

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert body["content"].startswith("The retrieved evidence does not support")
    assert body["trace"][0]["detail"] == "0 matching evaluation sources"
    assert "(no evidence retrieved)" in inference_client.calls[0][0]


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
    inference_client: StubInferenceClient,
) -> None:
    response = client.post("/answer", json={"question": question})

    assert response.status_code == 422
    assert retrieval_client.calls == []
    assert inference_client.calls == []


def test_answer_accepts_the_question_length_limit() -> None:
    response = client.post("/answer", json={"question": "a" * 4000})

    assert response.status_code == 200


def test_answer_rejects_questions_over_the_length_limit(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    response = client.post("/answer", json={"question": "a" * 4001})

    assert response.status_code == 422
    assert retrieval_client.calls == []
    assert inference_client.calls == []


def test_answer_rejects_unknown_request_fields(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    response = client.post(
        "/answer",
        json={"question": "Summarize the run", "unexpected": True},
    )

    assert response.status_code == 422
    assert retrieval_client.calls == []
    assert inference_client.calls == []


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
    inference_client: StubInferenceClient,
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
    assert inference_client.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            InferenceTimeoutError("private timeout detail"),
            504,
            "The inference service did not respond in time.",
        ),
        (
            InferenceClientError("private connection detail"),
            503,
            "The inference service is temporarily unavailable.",
        ),
        (
            InferenceResponseError("private malformed-output detail"),
            503,
            "The inference service is temporarily unavailable.",
        ),
    ],
)
def test_answer_translates_inference_failures(
    inference_client: StubInferenceClient,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    inference_client.error = error

    response = client.post(
        "/answer",
        json={"question": "What is slow?"},
        headers={"X-Request-ID": "agent-error-456"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert response.headers["X-Request-ID"] == "agent-error-456"
    assert str(error) not in response.text
