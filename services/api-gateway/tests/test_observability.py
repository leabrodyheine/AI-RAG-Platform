from api_gateway.main import app
from fastapi.testclient import TestClient


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    with TestClient(app) as client:
        client.post("/chat", json={})
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "http_server_request_duration_seconds" in response.text


def test_metrics_records_the_chat_route_under_the_gateway_service() -> None:
    with TestClient(app) as client:
        # A validation error still exercises the middleware and is counted.
        client.post("/chat", json={})
        body = client.get("/metrics").text

    assert 'service="api-gateway"' in body
    assert 'route="/chat"' in body


def test_request_id_is_returned_even_on_validation_error() -> None:
    with TestClient(app) as client:
        response = client.post("/chat", json={}, headers={"X-Request-ID": "gw-1"})

    assert response.status_code == 422
    assert response.headers["X-Request-ID"] == "gw-1"
