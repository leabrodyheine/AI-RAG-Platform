from agent_service.main import app
from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    client = TestClient(app)
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_server_requests_total" in response.text


def test_health_echoes_the_caller_request_id() -> None:
    response = TestClient(app).get("/health", headers={"X-Request-ID": "agent-obs-1"})

    assert response.headers["X-Request-ID"] == "agent-obs-1"


def test_downstream_failure_on_answer_is_recorded_as_5xx() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    # No retrieval/inference clients are configured in this bare app.
    client.post("/answer", json={"question": "why is p95 latency high?"})

    body = client.get("/metrics").text
    assert 'route="/answer"' in body
    assert 'status="5xx"' in body
