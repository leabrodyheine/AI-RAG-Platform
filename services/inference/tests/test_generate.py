from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from inference_service.backends.base import (
    GenerationResult,
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)
from inference_service.dependencies import get_backend
from inference_service.main import app

client = TestClient(app)


class StubBackend:
    model = "stub-model-v1"

    def __init__(self) -> None:
        self.result = GenerationResult(
            content="Grounded answer.",
            prompt_tokens=12,
            completion_tokens=2,
        )
        self.error: Exception | None = None
        self.calls: list[tuple[str, int, float]] = []

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        self.calls.append((prompt, max_tokens, temperature))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def backend() -> StubBackend:
    return StubBackend()


@pytest.fixture(autouse=True)
def override_backend(backend: StubBackend):
    app.dependency_overrides[get_backend] = lambda: backend
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_generate_returns_the_contract_response(backend: StubBackend) -> None:
    response = client.post(
        "/generate",
        json={
            "prompt": "Answer using only the evidence.",
            "maxTokens": 256,
            "temperature": 0.1,
        },
        headers={"X-Request-ID": "inference-request-1"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "inference-request-1"
    assert response.json() == {
        "content": "Grounded answer.",
        "model": "stub-model-v1",
        "usage": {"promptTokens": 12, "completionTokens": 2},
    }
    assert backend.calls == [("Answer using only the evidence.", 256, 0.1)]


def test_generate_assigns_a_request_id_when_the_caller_omits_one() -> None:
    response = client.post(
        "/generate",
        json={"prompt": "prompt", "maxTokens": 16, "temperature": 0},
    )

    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "", "maxTokens": 16, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 0, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 4096, "temperature": 0},
        {"prompt": "prompt", "maxTokens": 16, "temperature": 5},
        {"prompt": "prompt", "maxTokens": 16, "temperature": 0, "extra": True},
        {"maxTokens": 16, "temperature": 0},
    ],
)
def test_generate_rejects_invalid_requests(
    payload: dict[str, object],
    backend: StubBackend,
) -> None:
    response = client.post("/generate", json=payload)

    assert response.status_code == 422
    assert backend.calls == []


def test_generate_accepts_the_prompt_length_limit() -> None:
    response = client.post(
        "/generate",
        json={"prompt": "a" * 20_000, "maxTokens": 16, "temperature": 0},
    )

    assert response.status_code == 200


def test_generate_rejects_prompts_over_the_length_limit(backend: StubBackend) -> None:
    response = client.post(
        "/generate",
        json={"prompt": "a" * 20_001, "maxTokens": 16, "temperature": 0},
    )

    assert response.status_code == 422
    assert backend.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            InferenceBackendTimeoutError("private upstream timeout"),
            504,
            "The inference backend did not respond in time.",
        ),
        (
            InferenceBackendUnavailableError("private upstream failure"),
            503,
            "The inference backend is unavailable.",
        ),
    ],
)
def test_generate_translates_backend_failures(
    backend: StubBackend,
    error: Exception,
    expected_status: int,
    expected_detail: str,
) -> None:
    backend.error = error

    response = client.post(
        "/generate",
        json={"prompt": "prompt", "maxTokens": 16, "temperature": 0},
        headers={"X-Request-ID": "inference-error-1"},
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert response.headers["X-Request-ID"] == "inference-error-1"
    assert str(error) not in response.text
