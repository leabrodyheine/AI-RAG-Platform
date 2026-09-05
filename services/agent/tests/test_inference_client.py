from uuid import UUID

import httpx
import pytest
from agent_service.clients.inference import (
    InferenceClient,
    InferenceConnectionError,
    InferenceResponseError,
    InferenceTimeoutError,
)
from agent_service.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_generation_response() -> dict[str, object]:
    return {
        "content": "Based on the retrieved evidence, cache misses raised p95. [1]",
        "model": "deterministic-grounded-v1",
        "usage": {"promptTokens": 128, "completionTokens": 9},
    }


def client_for(handler) -> InferenceClient:
    return InferenceClient(
        httpx.AsyncClient(
            base_url="http://inference",
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.anyio
async def test_client_forwards_prompt_controls_and_request_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/generate"
        assert request.headers["X-Request-ID"] == "inference-request-123"
        assert request.content == (
            b'{"prompt":"grounded prompt","maxTokens":256,"temperature":0.2}'
        )
        return httpx.Response(200, json=valid_generation_response())

    client = client_for(handler)
    try:
        answer = await client.generate(
            "grounded prompt",
            max_tokens=256,
            temperature=0.2,
            request_id="inference-request-123",
        )
    finally:
        await client.aclose()

    assert answer.content.endswith("[1]")
    assert answer.model == "deterministic-grounded-v1"
    assert answer.prompt_tokens == 128
    assert answer.completion_tokens == 9


@pytest.mark.anyio
async def test_client_generates_a_request_id_and_uses_defaults() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        UUID(request.headers["X-Request-ID"])
        assert request.content == (
            b'{"prompt":"prompt","maxTokens":512,"temperature":0.1}'
        )
        return httpx.Response(200, json=valid_generation_response())

    client = client_for(handler)
    try:
        await client.generate("prompt")
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("raised_error", "expected_error"),
    [
        (httpx.ReadTimeout("timed out"), InferenceTimeoutError),
        (httpx.ConnectError("connection failed"), InferenceConnectionError),
        (httpx.RemoteProtocolError("bad response"), InferenceResponseError),
    ],
)
async def test_client_translates_transport_failures(
    raised_error: Exception,
    expected_error: type[Exception],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(raised_error, httpx.RequestError):
            raised_error.request = request
        raise raised_error

    client = client_for(handler)
    try:
        with pytest.raises(expected_error):
            await client.generate("prompt")
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_client_maps_an_upstream_timeout_status() -> None:
    client = client_for(lambda _: httpx.Response(504, json={"detail": "slow"}))
    try:
        with pytest.raises(InferenceTimeoutError):
            await client.generate("prompt")
    finally:
        await client.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"content": "", "model": "m", "usage": {}}),
        httpx.Response(
            200,
            json={"content": "answer", "model": "m", "usage": {"promptTokens": 1}},
        ),
        httpx.Response(
            200,
            json={
                "content": "answer",
                "model": "m",
                "usage": {"promptTokens": "1", "completionTokens": 2},
            },
        ),
        httpx.Response(503, json={"detail": "Unavailable"}),
    ],
)
async def test_client_rejects_invalid_responses(response: httpx.Response) -> None:
    client = client_for(lambda _: response)
    try:
        with pytest.raises(InferenceResponseError):
            await client.generate("prompt")
    finally:
        await client.aclose()


def test_agent_lifespan_closes_the_shared_inference_client() -> None:
    with TestClient(app):
        inference_client = app.state.inference_client
        assert inference_client.is_closed is False

    assert inference_client.is_closed is True
