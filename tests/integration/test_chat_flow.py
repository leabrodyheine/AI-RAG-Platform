import httpx
import pytest
from agent_service.clients.retrieval import RetrievalClient
from agent_service.dependencies import get_retrieval_client
from agent_service.main import app as agent_app
from api_gateway.clients.agent import AgentClient
from api_gateway.dependencies import get_agent_client
from api_gateway.main import app as gateway_app
from retrieval_service.main import app as retrieval_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_flows_from_the_gateway_through_the_agent() -> None:
    request_id = "integration-request-123"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=retrieval_app),
        base_url="http://retrieval",
    ) as retrieval_http_client:
        retrieval_client = RetrievalClient(retrieval_http_client)
        agent_app.dependency_overrides[get_retrieval_client] = lambda: retrieval_client

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_app),
            base_url="http://agent",
        ) as agent_http_client:
            agent_client = AgentClient(agent_http_client)
            gateway_app.dependency_overrides[get_agent_client] = lambda: agent_client
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

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert "strongest evidence for this performance investigation" in response.json()["content"]
    assert response.json()["citations"][0]["id"] == "retrieval-benchmark-1842"
    assert [step["label"] for step in response.json()["trace"]] == [
        "Retrieve",
        "Synthesize",
    ]
    assert response.json()["totalDurationMs"] >= 0
