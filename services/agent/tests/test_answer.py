from dataclasses import dataclass, field

import pytest
from agent_service.clients.inference import (
    GeneratedAnswer,
    InferenceClientError,
    InferenceResponseError,
    InferenceTimeoutError,
)
from agent_service.clients.retrieval import RetrievalClientError, RetrievalTimeoutError
from agent_service.dependencies import (
    get_inference_client,
    get_retrieval_client,
    get_workflow_config,
)
from agent_service.main import app
from agent_service.schemas import Citation
from agent_service.workflow import DIRECT_ANSWER, STEP_LIMIT_ANSWER, WorkflowConfig
from fastapi.testclient import TestClient

client = TestClient(app)


def citation(relevance: float, ident: str = "retrieval-benchmark-1842") -> Citation:
    return Citation(
        id=ident,
        title="Retrieval benchmark · run #1842",
        source="evaluation/performance/retrieval.json",
        excerpt="Cache misses increased vector-search p95 from 112 ms to 391 ms.",
        relevance=relevance,
    )


@dataclass
class StubRetrievalClient:
    results: list[Citation] = field(default_factory=lambda: [citation(0.9)])
    result_map: dict[str, list[Citation]] | None = None
    error: Exception | None = None
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        request_id: str | None = None,
    ) -> list[Citation]:
        self.calls.append((query, request_id))
        if self.error:
            raise self.error
        if self.result_map is not None:
            return self.result_map.get(query, [])
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


@pytest.fixture
def workflow_config() -> WorkflowConfig:
    return WorkflowConfig()


@pytest.fixture(autouse=True)
def override_dependencies(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
    workflow_config: WorkflowConfig,
):
    app.dependency_overrides[get_retrieval_client] = lambda: retrieval_client
    app.dependency_overrides[get_inference_client] = lambda: inference_client
    app.dependency_overrides[get_workflow_config] = lambda: workflow_config
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def labels(body: dict) -> list[str]:
    return [step["label"] for step in body["trace"]]


def test_answer_runs_the_retrieve_assess_generate_path(
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
    assert body["citations"] == [citation(0.9).model_dump(by_alias=True)]
    assert labels(body) == ["Plan", "Retrieve", "Assess evidence", "Generate"]
    assert body["trace"][0]["detail"] == "question needs evaluation evidence"
    assert body["trace"][1]["detail"] == "1 source, top relevance 0.90"
    assert "top 0.90" in body["trace"][2]["detail"]
    assert body["trace"][3]["detail"] == (
        "deterministic-grounded-v1 produced 9 completion tokens from 64 prompt tokens"
    )
    assert retrieval_client.calls == [("What is driving p95 latency?", "agent-request-123")]
    assert inference_client.calls[0][1] == "agent-request-123"


def test_answer_sends_a_grounded_prompt_to_inference(
    inference_client: StubInferenceClient,
) -> None:
    response = client.post("/answer", json={"question": "What is driving p95 latency?"})

    assert response.status_code == 200
    prompt = inference_client.calls[0][0]
    assert "Question: What is driving p95 latency?" in prompt
    assert (
        "[1] Retrieval benchmark · run #1842 — "
        "Cache misses increased vector-search p95 from 112 ms to 391 ms."
    ) in prompt


def test_answer_responds_directly_without_retrieval_or_inference(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    response = client.post("/answer", json={"question": "What can you do?"})

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == DIRECT_ANSWER
    assert body["citations"] == []
    assert labels(body) == ["Plan", "Answer directly"]
    assert retrieval_client.calls == []
    assert inference_client.calls == []


def test_answer_rewrites_a_weak_query_and_keeps_the_stronger_evidence(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    strong = citation(0.82, "rewrite-hit")
    retrieval_client.result_map = {
        "Why did the cache p95 regress badly?": [citation(0.12, "weak-hit")],
        "cache p95 regress badly": [strong],
    }

    response = client.post(
        "/answer",
        json={"question": "Why did the cache p95 regress badly?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [c["id"] for c in body["citations"]] == ["rewrite-hit"]
    assert labels(body) == [
        "Plan",
        "Retrieve",
        "Assess evidence",
        "Rewrite query",
        "Retrieve after rewrite",
        "Assess evidence after rewrite",
        "Generate",
    ]
    assert body["trace"][3]["detail"] == "retrying as: cache p95 regress badly"
    assert [call[0] for call in retrieval_client.calls] == [
        "Why did the cache p95 regress badly?",
        "cache p95 regress badly",
    ]
    assert "[1] Retrieval benchmark · run #1842" in inference_client.calls[0][0]


def test_answer_reports_insufficient_evidence_without_fabricating_citations(
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

    response = client.post("/answer", json={"question": "snowfall totals tomorrow"})

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert body["content"].startswith("The retrieved evidence does not support")
    assert body["trace"][2]["detail"] == "no sources retrieved"
    assert "(no evidence retrieved)" in inference_client.calls[0][0]


def test_answer_drops_evidence_below_the_relevance_threshold(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
) -> None:
    retrieval_client.results = [citation(0.05, "noise-hit")]

    response = client.post("/answer", json={"question": "Why did the run regress?"})

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "(no evidence retrieved)" in inference_client.calls[0][0]


def test_answer_halts_at_the_step_limit_before_generating(
    retrieval_client: StubRetrievalClient,
    inference_client: StubInferenceClient,
    workflow_config: WorkflowConfig,
) -> None:
    workflow_config = WorkflowConfig(max_steps=1)
    app.dependency_overrides[get_workflow_config] = lambda: workflow_config

    response = client.post("/answer", json={"question": "What is driving p95 latency?"})

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == STEP_LIMIT_ANSWER
    assert body["citations"] == []
    assert labels(body) == ["Plan", "Retrieve", "Assess evidence", "Stop"]
    assert body["trace"][-1]["detail"] == "step limit reached before generation"
    assert inference_client.calls == []


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
