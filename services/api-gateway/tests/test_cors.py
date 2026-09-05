from api_gateway.main import app
from fastapi.testclient import TestClient


def test_chat_preflight_allows_the_local_vite_origin() -> None:
    response = TestClient(app).options(
        "/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]
    assert "content-type" in response.headers["Access-Control-Allow-Headers"].lower()
    assert "x-request-id" in response.headers["Access-Control-Allow-Headers"].lower()


def test_responses_expose_request_ids_to_allowed_origins() -> None:
    response = TestClient(app).get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers["Access-Control-Expose-Headers"] == "X-Request-ID"
    assert "X-Request-ID" in response.headers


def test_chat_preflight_rejects_an_unconfigured_origin() -> None:
    response = TestClient(app).options(
        "/chat",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers
