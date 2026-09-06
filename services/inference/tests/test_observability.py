from fastapi.testclient import TestClient
from inference_service.main import app


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    with TestClient(app) as client:
        client.post(
            "/generate",
            json={"prompt": "[1] latency — p95 rose to 391 ms", "maxTokens": 64, "temperature": 0},
        )
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_server_requests_total" in response.text
    assert 'service="inference"' in response.text


def test_generate_echoes_request_id_and_is_counted() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/generate",
            json={"prompt": "[1] latency — p95 rose to 391 ms", "maxTokens": 64, "temperature": 0},
            headers={"X-Request-ID": "inference-obs-1"},
        )
        body = client.get("/metrics").text

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "inference-obs-1"
    assert 'route="/generate"' in body
