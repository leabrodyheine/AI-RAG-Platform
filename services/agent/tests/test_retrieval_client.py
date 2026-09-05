from uuid import UUID

import httpx
import pytest
from agent_service.clients.retrieval import (
    RetrievalClient,
    RetrievalConnectionError,
    RetrievalResponseError,
    RetrievalTimeoutError,
)
from agent_service.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_search_response() -> dict[str, object]:
    return {
        "results": [
            {
                "id": "evidence-1",
                "title": "Evidence",
                "source": "evaluation/result.json",
                "excerpt": "Measured result",
                "relevance": 0.85,
            }
        ]
    }


@pytest.mark.anyio
async def test_retrieval_client_forwards_query_limit_and_request_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.headers["X-Request-ID"] == "retrieval-request-123"
        assert request.content == b'{"query":"What is slow?","topK":2}'
        return httpx.Response(200, json=valid_search_response())

    client = RetrievalClient(
        httpx.AsyncClient(base_url="http://retrieval", transport=httpx.MockTransport(handler))
    )
    try:
        results = await client.search(
            "What is slow?",
            top_k=2,
            request_id="retrieval-request-123",
        )
    finally:
        await client.aclose()

    assert len(results) == 1
    assert results[0].id == "evidence-1"
    assert results[0].relevance == 0.85


@pytest.mark.anyio
async def test_retrieval_client_generates_a_request_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        UUID(request.headers["X-Request-ID"])
        return httpx.Response(200, json={"results": []})

    client = RetrievalClient(
        httpx.AsyncClient(base_url="http://retrieval", transport=httpx.MockTransport(handler))
    )
    try:
        assert await client.search("Summarize the run") == []
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (httpx.ReadTimeout("timed out"), RetrievalTimeoutError),
        (httpx.ConnectError("connection failed"), RetrievalConnectionError),
        (httpx.RemoteProtocolError("bad response"), RetrievalResponseError),
    ],
)
async def test_retrieval_client_translates_transport_failures(
    raised_error: Exception,
    expected_error: type[Exception],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(raised_error, httpx.RequestError):
            raised_error.request = request
        raise raised_error

    client = RetrievalClient(
        httpx.AsyncClient(base_url="http://retrieval", transport=httpx.MockTransport(handler))
    )
    try:
        with pytest.raises(expected_error):
            await client.search("What is slow?")
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"results": "not-a-list"}),
        httpx.Response(200, json={"results": [{"id": "incomplete"}]}),
        httpx.Response(503, json={"detail": "Unavailable"}),
    ],
)
async def test_retrieval_client_rejects_invalid_responses(response: httpx.Response) -> None:
    client = RetrievalClient(
        httpx.AsyncClient(
            base_url="http://retrieval",
            transport=httpx.MockTransport(lambda _: response),
        )
    )
    try:
        with pytest.raises(RetrievalResponseError):
            await client.search("What is slow?")
    finally:
        await client.aclose()


def test_agent_lifespan_closes_the_shared_retrieval_client() -> None:
    with TestClient(app):
        retrieval_client = app.state.retrieval_client
        assert retrieval_client.is_closed is False

    assert retrieval_client.is_closed is True
