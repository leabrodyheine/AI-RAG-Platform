from uuid import UUID

import httpx
import pytest
from api_gateway.clients.agent import (
    AgentClient,
    AgentConnectionError,
    AgentResponseError,
    AgentTimeoutError,
)
from api_gateway.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_answer() -> dict[str, object]:
    return {
        "content": "Development answer",
        "citations": [],
        "trace": [{"label": "Agent", "detail": "Development response", "durationMs": 1}],
        "totalDurationMs": 1,
    }


@pytest.mark.anyio
async def test_agent_client_forwards_question_and_request_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/answer"
        assert request.headers["X-Request-ID"] == "request-123"
        assert request.content == b'{"question":"What is slow?"}'
        return httpx.Response(200, json=valid_answer())

    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(handler),
        )
    )

    try:
        result = await client.answer("What is slow?", request_id="request-123")
    finally:
        await client.aclose()

    assert result.payload == valid_answer()
    assert result.request_id == "request-123"


@pytest.mark.anyio
async def test_agent_client_generates_a_request_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        UUID(request.headers["X-Request-ID"])
        return httpx.Response(200, json=valid_answer())

    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(handler),
        )
    )

    try:
        result = await client.answer("Summarize the run")
    finally:
        await client.aclose()

    UUID(result.request_id)


@pytest.mark.anyio
async def test_agent_client_distinguishes_timeouts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(handler),
        )
    )

    try:
        with pytest.raises(AgentTimeoutError):
            await client.answer("What is slow?")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_agent_client_distinguishes_connection_failures() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(handler),
        )
    )

    try:
        with pytest.raises(AgentConnectionError):
            await client.answer("What is slow?")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_agent_client_rejects_protocol_failures() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("invalid response framing")

    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(handler),
        )
    )

    try:
        with pytest.raises(AgentResponseError):
            await client.answer("What is slow?")
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"content": "Missing fields"}),
        httpx.Response(503, json={"detail": "Unavailable"}),
    ],
)
async def test_agent_client_rejects_invalid_responses(response: httpx.Response) -> None:
    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(lambda _: response),
        )
    )

    try:
        with pytest.raises(AgentResponseError):
            await client.answer("What is slow?")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_agent_client_preserves_an_upstream_timeout() -> None:
    client = AgentClient(
        httpx.AsyncClient(
            base_url="http://agent:8001",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(504, json={"detail": "Retrieval timed out"})
            ),
        )
    )

    try:
        with pytest.raises(AgentTimeoutError):
            await client.answer("What is slow?")
    finally:
        await client.aclose()


def test_gateway_lifespan_closes_the_shared_agent_client() -> None:
    with TestClient(app):
        agent_client = app.state.agent_client
        assert agent_client.is_closed is False

    assert agent_client.is_closed is True
