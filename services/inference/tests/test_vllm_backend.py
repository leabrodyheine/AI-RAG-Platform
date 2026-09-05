import json
from collections.abc import Callable

import httpx
import pytest
from inference_service.backends import VLLMBackend, create_backend
from inference_service.backends.base import (
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)
from inference_service.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def openai_completion() -> dict[str, object]:
    return {
        "id": "cmpl-1",
        "object": "text_completion",
        "model": "meta-llama/Meta-Llama-3-8B-Instruct",
        "choices": [{"index": 0, "text": " Cache misses raised p95. [1]", "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 220, "completion_tokens": 8, "total_tokens": 228},
    }


def backend_for(handler: Handler, *, stop_sequences: tuple[str, ...] = ()) -> VLLMBackend:
    return VLLMBackend(
        base_url="http://vllm:8000",
        model="meta-llama/Meta-Llama-3-8B-Instruct",
        timeout_seconds=5,
        stop_sequences=stop_sequences,
        client=httpx.AsyncClient(
            base_url="http://vllm:8000",
            transport=httpx.MockTransport(handler),
        ),
    )


@pytest.mark.anyio
async def test_generate_maps_the_openai_text_completion() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/completions"
        body = json.loads(request.content)
        assert body == {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "prompt": "grounded prompt",
            "max_tokens": 256,
            "temperature": 0.1,
            "stream": False,
        }
        return httpx.Response(200, json=openai_completion())

    backend = backend_for(handler)
    try:
        result = await backend.generate("grounded prompt", max_tokens=256, temperature=0.1)
    finally:
        await backend.aclose()

    assert result.content == " Cache misses raised p95. [1]"
    assert result.prompt_tokens == 220
    assert result.completion_tokens == 8


@pytest.mark.anyio
async def test_generate_sends_configured_stop_sequences() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stop"] == ["\\n\\n", "User:"]
        return httpx.Response(200, json=openai_completion())

    backend = backend_for(handler, stop_sequences=("\\n\\n", "User:"))
    try:
        await backend.generate("grounded prompt", max_tokens=32, temperature=0.0)
    finally:
        await backend.aclose()


@pytest.mark.anyio
async def test_generate_translates_a_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    backend = backend_for(handler)
    try:
        with pytest.raises(InferenceBackendTimeoutError):
            await backend.generate("prompt", max_tokens=16, temperature=0.0)
    finally:
        await backend.aclose()


@pytest.mark.anyio
async def test_generate_translates_a_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    backend = backend_for(handler)
    try:
        with pytest.raises(InferenceBackendUnavailableError):
            await backend.generate("prompt", max_tokens=16, temperature=0.0)
    finally:
        await backend.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, text="loading"),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200,
            json={
                "choices": [{"text": "  "}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        ),
        httpx.Response(200, json={"choices": [{"text": "answer"}]}),
        httpx.Response(
            200,
            json={
                "choices": [{"text": "answer"}],
                "usage": {"prompt_tokens": "1", "completion_tokens": 1},
            },
        ),
    ],
)
async def test_generate_rejects_unusable_responses(response: httpx.Response) -> None:
    backend = backend_for(lambda _: response)
    try:
        with pytest.raises(InferenceBackendUnavailableError):
            await backend.generate("prompt", max_tokens=16, temperature=0.0)
    finally:
        await backend.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("health", "expected"),
    [
        (httpx.Response(200), True),
        (httpx.Response(503), False),
    ],
)
async def test_ready_follows_the_health_endpoint(
    health: httpx.Response,
    expected: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/health"
        return health

    backend = backend_for(handler)
    try:
        assert await backend.ready() is expected
    finally:
        await backend.aclose()


@pytest.mark.anyio
async def test_ready_is_false_when_the_server_is_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    backend = backend_for(handler)
    try:
        assert await backend.ready() is False
    finally:
        await backend.aclose()


def test_create_backend_builds_the_vllm_backend() -> None:
    backend = create_backend(
        Settings(
            backend="vllm",
            model="meta-llama/Meta-Llama-3-8B-Instruct",
            backend_timeout_seconds=30,
            backend_base_url="http://vllm:8000",
            stop_sequences=("</s>",),
        )
    )

    assert isinstance(backend, VLLMBackend)
    assert backend.name == "vllm"
    assert backend.model == "meta-llama/Meta-Llama-3-8B-Instruct"
