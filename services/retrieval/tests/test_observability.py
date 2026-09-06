from fastapi.testclient import TestClient
from retrieval_service.main import app


def test_metrics_endpoint_exposes_prometheus_text() -> None:
    client = TestClient(app)
    client.post("/search", json={"query": "cache latency", "topK": 3})

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "http_server_requests_total" in response.text
    assert 'service="retrieval"' in response.text


def test_search_echoes_request_id_and_is_counted() -> None:
    client = TestClient(app)

    response = client.post(
        "/search",
        json={"query": "cache latency", "topK": 3},
        headers={"X-Request-ID": "retrieval-obs-1"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "retrieval-obs-1"
    assert 'route="/search"' in client.get("/metrics").text
