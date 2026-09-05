import httpx
import pytest
from agent_service.main import app as agent_app
from api_gateway.clients.agent import AgentClient
from api_gateway.dependencies import get_agent_client
from api_gateway.main import app as gateway_app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_chat_flows_from_the_gateway_through_the_agent() -> None:
    request_id = "integration-request-123"

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

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json()["content"].startswith(
        "The development agent classified this as a performance investigation."
    )
    assert response.json()["citations"] == []
    assert response.json()["trace"][0]["label"] == "Agent"
    assert response.json()["totalDurationMs"] >= 0
