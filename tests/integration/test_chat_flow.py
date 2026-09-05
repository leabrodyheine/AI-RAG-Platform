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
from retrieval_service.main import app as retrieval_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_flows_from_the_browser_through_retrieval_and_inference() -> None:
    request_id = "integration-request-123"
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
    body = response.json()
    assert body["citations"][0]["id"] == "retrieval-benchmark-1842"
    assert body["content"].startswith("Based on the retrieved evidence,")
    assert body["content"].rstrip().endswith("[1]")
    assert [step["label"] for step in body["trace"]] == ["Retrieve", "Generate"]
    assert body["trace"][1]["detail"].startswith("deterministic-grounded-v1 produced ")
    assert body["totalDurationMs"] >= 0
