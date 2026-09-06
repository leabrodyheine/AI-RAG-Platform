"""A single chat request must be followable end to end.

This drives the real browser -> gateway -> agent -> retrieval -> inference path
(the same wiring as ``test_chat_flow``) and asserts that one request id and one
trace id are shared by every service that touches the request.
"""

import httpx
import pytest
from agent_service.clients.inference import InferenceClient
from agent_service.clients.retrieval import RetrievalClient
from agent_service.dependencies import get_inference_client, get_retrieval_client
from agent_service.main import app as agent_app
from api_gateway.clients.agent import AgentClient
from api_gateway.dependencies import get_agent_client
from api_gateway.main import app as gateway_app
from inference_service.backends import DeterministicBackend
from inference_service.dependencies import get_backend
from inference_service.main import app as inference_app
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from retrieval_service.main import app as retrieval_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def exported_spans():
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):  # pragma: no cover - defensive
        pytest.skip("no SDK tracer provider configured")
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    try:
        yield exporter
    finally:
        exporter.clear()
        processor.shutdown()


@pytest.mark.anyio
async def test_one_request_id_and_trace_id_span_every_service(exported_spans) -> None:
    request_id = "browser-trace-abc123"
    inference_app.dependency_overrides[get_backend] = lambda: DeterministicBackend(
        model="deterministic-grounded-v1"
    )

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=retrieval_app),
            base_url="http://retrieval",
        ) as retrieval_http_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=inference_app),
            base_url="http://inference",
        ) as inference_http_client,
    ):
        agent_app.dependency_overrides[get_retrieval_client] = lambda: RetrievalClient(
            retrieval_http_client
        )
        agent_app.dependency_overrides[get_inference_client] = lambda: InferenceClient(
            inference_http_client
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app),
            base_url="http://agent",
        ) as agent_http_client:
            gateway_app.dependency_overrides[get_agent_client] = lambda: AgentClient(
                agent_http_client
            )
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=gateway_app),
                    base_url="http://gateway",
                ) as browser_client:
                    response = await browser_client.post(
                        "/chat",
                        json={"question": "What is driving p95 latency?"},
                        headers={"X-Request-ID": request_id},
                    )
            finally:
                gateway_app.dependency_overrides.clear()
                agent_app.dependency_overrides.clear()
                inference_app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id

    # The per-request route span each service's HTTP instrumentation emits.
    route_spans = {
        span.attributes["http.route"]: span
        for span in exported_spans.get_finished_spans()
        if span.attributes.get("http.route")
    }
    assert {"/chat", "/answer", "/search", "/generate"} <= set(route_spans)

    trace_ids = {span.context.trace_id for span in route_spans.values()}
    assert len(trace_ids) == 1, "every service must share one trace"

    for route in ("/chat", "/answer", "/search", "/generate"):
        assert route_spans[route].attributes.get("rag.request_id") == request_id


@pytest.mark.anyio
async def test_workflow_decision_spans_are_recorded(exported_spans) -> None:
    inference_app.dependency_overrides[get_backend] = lambda: DeterministicBackend(
        model="deterministic-grounded-v1"
    )

    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=retrieval_app),
            base_url="http://retrieval",
        ) as retrieval_http_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=inference_app),
            base_url="http://inference",
        ) as inference_http_client,
    ):
        agent_app.dependency_overrides[get_retrieval_client] = lambda: RetrievalClient(
            retrieval_http_client
        )
        agent_app.dependency_overrides[get_inference_client] = lambda: InferenceClient(
            inference_http_client
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=agent_app),
                base_url="http://agent",
            ) as agent_client:
                await agent_client.post(
                    "/answer",
                    json={"question": "What is driving p95 latency?"},
                    headers={"X-Request-ID": "agent-span-1"},
                )
        finally:
            agent_app.dependency_overrides.clear()
            inference_app.dependency_overrides.clear()

    names = {span.name for span in exported_spans.get_finished_spans()}
    assert {"agent.plan", "agent.retrieve", "agent.assess", "agent.generate"} <= names
    assert "retrieval.search" in names
    assert "inference.generate" in names
