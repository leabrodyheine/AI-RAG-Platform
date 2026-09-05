import pytest
from fastapi.testclient import TestClient
from inference_service.backends import DeterministicBackend
from inference_service.dependencies import get_backend
from inference_service.main import app


def test_health_reports_process_liveness() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "inference", "status": "ok"}


def test_readiness_reports_the_active_backend_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "deterministic")
    monkeypatch.setenv("INFERENCE_MODEL", "local-test-model")

    with TestClient(app) as running:
        response = running.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "service": "inference",
        "status": "ready",
        "backend": "deterministic",
        "model": "local-test-model",
    }


def test_readiness_returns_503_until_the_model_is_ready() -> None:
    class LoadingBackend:
        name = "vllm"
        model = "meta-llama/Meta-Llama-3-8B-Instruct"

        async def ready(self) -> bool:
            return False

    app.dependency_overrides[get_backend] = lambda: LoadingBackend()
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "service": "inference",
        "status": "not_ready",
        "backend": "vllm",
        "model": "meta-llama/Meta-Llama-3-8B-Instruct",
    }


def test_readiness_treats_a_failing_check_as_not_ready() -> None:
    class BrokenBackend:
        name = "triton"
        model = "ensemble"

        async def ready(self) -> bool:
            raise RuntimeError("connection reset")

    app.dependency_overrides[get_backend] = lambda: BrokenBackend()
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_lifespan_builds_and_releases_the_configured_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "deterministic")

    with TestClient(app):
        assert isinstance(app.state.backend, DeterministicBackend)

    assert app.state.backend is None
