from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from retrieval_service.main import app


def test_lifespan_connects_and_closes_configured_document_store(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://rag:secret@postgres/platform")
    document_store = AsyncMock()

    with (
        patch(
            "retrieval_service.main.DocumentStore.connect",
            AsyncMock(return_value=document_store),
        ) as connect,
        TestClient(app),
    ):
        connect.assert_awaited_once_with("postgresql://rag:secret@postgres/platform")
        assert app.state.document_store is document_store

    document_store.close.assert_awaited_once()


def test_lifespan_uses_in_memory_mode_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with TestClient(app):
        assert app.state.document_store is None
