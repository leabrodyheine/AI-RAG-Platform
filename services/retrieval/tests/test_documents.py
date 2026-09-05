from uuid import UUID

from fastapi.testclient import TestClient
from retrieval_service.dependencies import get_document_store
from retrieval_service.main import app

client = TestClient(app)

DOCUMENT = {
    "id": "load-test-42",
    "title": "Load test 42",
    "source": "evaluation/performance/load-test-42.json",
    "content": "The run sustained 18 requests per second.",
    "tags": ["performance", "throughput"],
}


class RecordingStore:
    def __init__(self) -> None:
        self.documents = []

    async def upsert_documents(self, documents) -> int:
        self.documents.extend(documents)
        return len(documents)


def test_documents_upserts_a_valid_batch_and_propagates_request_id() -> None:
    store = RecordingStore()
    app.dependency_overrides[get_document_store] = lambda: store
    try:
        response = client.post(
            "/documents",
            json={"documents": [DOCUMENT]},
            headers={"X-Request-ID": "ingestion-123"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "ingestion-123"
    assert response.json() == {"upserted": 1}
    assert store.documents[0].id == "load-test-42"


def test_documents_generates_a_request_id() -> None:
    app.dependency_overrides[get_document_store] = lambda: RecordingStore()
    try:
        response = client.post("/documents", json={"documents": [DOCUMENT]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    UUID(response.headers["X-Request-ID"])


def test_documents_requires_persistent_storage() -> None:
    app.dependency_overrides[get_document_store] = lambda: None
    try:
        response = client.post("/documents", json={"documents": [DOCUMENT]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Persistent document storage is not configured."}


def test_documents_validates_input_before_using_storage() -> None:
    app.dependency_overrides[get_document_store] = lambda: RecordingStore()
    try:
        response = client.post("/documents", json={"documents": []})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
