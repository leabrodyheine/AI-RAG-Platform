from fastapi.testclient import TestClient
from retrieval_service.dependencies import get_document_store
from retrieval_service.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "retrieval", "status": "ok"}


def test_readiness_reports_in_memory_mode_without_a_database() -> None:
    response = TestClient(app).get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "service": "retrieval",
        "status": "ready",
        "storage": "memory",
    }


def test_readiness_checks_persistent_storage() -> None:
    class ReadyStore:
        async def is_ready(self) -> bool:
            return True

    app.dependency_overrides[get_document_store] = lambda: ReadyStore()
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["storage"] == "postgres"


def test_readiness_hides_storage_failures() -> None:
    class FailedStore:
        async def is_ready(self) -> bool:
            raise RuntimeError("database credentials must not leak")

    app.dependency_overrides[get_document_store] = lambda: FailedStore()
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "service": "retrieval",
        "status": "not_ready",
        "storage": "postgres",
    }
