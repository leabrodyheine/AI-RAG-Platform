from dataclasses import dataclass, field
from uuid import UUID

import pytest
from api_gateway.clients.agent import (
    AgentAnswer,
    AgentConnectionError,
    AgentResponseError,
    AgentTimeoutError,
)
from api_gateway.dependencies import get_agent_client
from api_gateway.main import app
from fastapi.testclient import TestClient
from httpx import Response


def valid_answer() -> dict[str, object]:
    return {
        "content": "Development answer",
        "citations": [],
        "trace": [{"label": "Agent", "detail": "Development response", "durationMs": 3}],
        "totalDurationMs": 3,
    }


@dataclass
class StubAgentClient:
    result: AgentAnswer | None = None
    error: Exception | None = None
    calls: list[tuple[str, str | None]] = field(default_factory=list)

    async def answer(self, question: str, request_id: str | None = None) -> AgentAnswer:
        self.calls.append((question, request_id))
        if self.error:
            raise self.error
        if self.result is not None:
            return self.result
        assert request_id is not None
        return AgentAnswer(payload=valid_answer(), request_id=request_id)


def request_with(stub: StubAgentClient, **kwargs: object) -> Response:
    app.dependency_overrides[get_agent_client] = lambda: stub
    try:
        with TestClient(app) as client:
            return client.post("/chat", **kwargs)
    finally:
        app.dependency_overrides.clear()


def test_chat_forwards_the_question_and_preserves_the_agent_response() -> None:
    stub = StubAgentClient(
        result=AgentAnswer(payload=valid_answer(), request_id="request-123")
    )

    response = request_with(
        stub,
        json={"question": "  What is slow?  "},
        headers={"X-Request-ID": "request-123"},
    )

    assert response.status_code == 200
    assert response.json() == valid_answer()
    assert response.headers["X-Request-ID"] == "request-123"
    assert stub.calls == [("What is slow?", "request-123")]


def test_chat_generates_a_request_id_when_missing() -> None:
    stub = StubAgentClient()

    response = request_with(stub, json={"question": "What is slow?"})

    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])
    assert stub.calls[0][1] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (AgentConnectionError("connection failed"), 503, "agent_unavailable"),
        (AgentResponseError("invalid response"), 503, "agent_unavailable"),
        (AgentTimeoutError("timed out"), 504, "agent_timeout"),
    ],
)
def test_chat_translates_agent_failures(
    error: Exception,
    expected_status: int,
    expected_code: str,
) -> None:
    stub = StubAgentClient(error=error)

    response = request_with(
        stub,
        json={"question": "What is slow?"},
        headers={"X-Request-ID": "request-456"},
    )

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert response.json()["requestId"] == "request-456"
    assert response.headers["X-Request-ID"] == "request-456"
    assert str(error) not in response.json()["message"]


def test_chat_rejects_an_invalid_agent_response_without_leaking_details() -> None:
    stub = StubAgentClient(
        result=AgentAnswer(
            payload={"content": "incomplete upstream response"},
            request_id="request-invalid",
        )
    )

    response = request_with(
        stub,
        json={"question": "What is slow?"},
        headers={"X-Request-ID": "request-invalid"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "code": "agent_unavailable",
        "message": "The agent service is temporarily unavailable.",
        "requestId": "request-invalid",
    }


def test_chat_returns_a_contract_shaped_validation_error() -> None:
    stub = StubAgentClient()

    response = request_with(
        stub,
        json={"question": "   "},
        headers={"X-Request-ID": "request-789"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "validation_error",
        "message": "The chat request failed validation.",
        "requestId": "request-789",
    }
    assert response.headers["X-Request-ID"] == "request-789"
    assert stub.calls == []
