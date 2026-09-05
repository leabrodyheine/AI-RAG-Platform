import pytest
from fastapi.testclient import TestClient
from inference_service.backends import DeterministicBackend
from inference_service.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "inference", "status": "ok"}


def test_readiness_reports_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "deterministic")
    monkeypatch.setenv("INFERENCE_MODEL", "local-test-model")

    with TestClient(app) as running:
        response = running.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "service": "inference",
        "status": "ready",
        "model": "local-test-model",
    }


def test_lifespan_builds_and_releases_the_configured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "deterministic")

    with TestClient(app):
        assert isinstance(app.state.backend, DeterministicBackend)

    assert app.state.backend is None
