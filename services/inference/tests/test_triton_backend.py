import json
from collections.abc import Callable

import httpx
import pytest
from inference_service.backends import TritonBackend, create_backend
from inference_service.backends.base import (
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)
from inference_service.config import Settings

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def backend_for(
    handler: Handler,
    *,
    model: str = "ensemble",
    stop_sequences: tuple[str, ...] = (),
) -> TritonBackend:
    return TritonBackend(
        base_url="http://triton:8000",
        model=model,
        timeout_seconds=5,
        stop_sequences=stop_sequences,
        client=httpx.AsyncClient(
            base_url="http://triton:8000",
            transport=httpx.MockTransport(handler),
        ),
    )


@pytest.mark.anyio
async def test_generate_maps_the_kserve_generate_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v2/models/ensemble/generate"
        assert json.loads(request.content) == {
            "text_input": "grounded prompt here",
            "max_tokens": 128,
            "temperature": 0.2,
            "stream": False,
        }
        return httpx.Response(
            200,
            json={
                "model_name": "ensemble",
                "model_version": "1",
                "text_output": "Cache misses raised p95. [1]",
            },
        )

    backend = backend_for(handler)
    try:
        result = await backend.generate(
            "grounded prompt here",
            max_tokens=128,
            temperature=0.2,
        )
    finally:
        await backend.aclose()

    assert result.content == "Cache misses raised p95. [1]"
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 5


@pytest.mark.anyio
async def test_generate_sends_configured_stop_words() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stop_words"] == ["</s>"]
        return httpx.Response(200, json={"text_output": "answer"})

    backend = backend_for(handler, stop_sequences=("</s>",))
    try:
        await backend.generate("prompt", max_tokens=16, temperature=0.0)
    finally:
        await backend.aclose()


@pytest.mark.anyio
async def test_generate_encodes_the_model_name_in_the_path() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.raw_path == b"/v2/models/llm%2Fv1/generate"
        return httpx.Response(200, json={"text_output": "answer"})

    backend = backend_for(handler, model="llm/v1")
    try:
        await backend.generate("prompt", max_tokens=16, temperature=0.0)
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
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error": "bad request"}),
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"model_name": "ensemble"}),
        httpx.Response(200, json={"text_output": "   "}),
        httpx.Response(200, json={"text_output": 123}),
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
    [(httpx.Response(200), True), (httpx.Response(503), False)],
)
async def test_ready_follows_the_model_ready_endpoint(
    health: httpx.Response,
    expected: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v2/models/ensemble/ready"
        return health

    backend = backend_for(handler)
    try:
        assert await backend.ready() is expected
    finally:
        await backend.aclose()


def test_create_backend_builds_the_triton_backend() -> None:
    backend = create_backend(
        Settings(
            backend="triton",
            model="ensemble",
            backend_timeout_seconds=30,
            backend_base_url="http://triton:8000",
            stop_sequences=(),
        )
    )

    assert isinstance(backend, TritonBackend)
    assert backend.name == "triton"
    assert backend.model == "ensemble"
