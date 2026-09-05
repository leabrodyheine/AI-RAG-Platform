from agent_service.main import app
from fastapi.testclient import TestClient


def test_answer_returns_a_contract_compatible_development_response() -> None:
    response = TestClient(app).post(
        "/answer",
        json={"question": "What is driving p95 latency?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"].startswith("The development agent classified this as a performance")
    assert body["citations"] == []
    assert body["trace"][0]["label"] == "Agent"
    assert body["trace"][0]["detail"] == (
        "Performance question routed to the development workflow"
    )
    assert body["trace"][0]["durationMs"] >= 0
    assert body["totalDurationMs"] >= 0
