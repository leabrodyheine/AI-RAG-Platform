from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from retrieval_service.main import app


def test_lifespan_connects_and_closes_configured_document_store(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://rag:secret@postgres/platform")
    monkeypatch.delenv("REDIS_URL", raising=False)
    document_store = AsyncMock()
    embedding_provider = object()

    with (
        patch(
            "retrieval_service.main.create_embedding_provider",
            return_value=embedding_provider,
        ) as create_provider,
        patch(
            "retrieval_service.main.DocumentStore.connect",
            AsyncMock(return_value=document_store),
        ) as connect,
        TestClient(app),
    ):
        create_provider.assert_called_once_with(
            "fastembed",
            model_name="BAAI/bge-small-en-v1.5",
            model_version="fastembed:BAAI/bge-small-en-v1.5:v1",
            cache_dir=None,
        )
        connect.assert_awaited_once_with(
            "postgresql://rag:secret@postgres/platform",
            embedding_provider,
        )
        assert app.state.document_store is document_store
        assert app.state.retrieval_cache is None

    document_store.close.assert_awaited_once()
    assert app.state.document_store is None


def test_lifespan_uses_in_memory_mode_without_database_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")

    with (
        patch("retrieval_service.main.create_embedding_provider") as create_provider,
        TestClient(app),
    ):
        assert app.state.document_store is None
        assert app.state.retrieval_cache is None

    create_provider.assert_not_called()


def test_lifespan_creates_and_closes_configured_retrieval_cache(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://rag:secret@postgres/platform")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("RETRIEVAL_CACHE_TTL_SECONDS", "120")
    document_store = AsyncMock()
    retrieval_cache = AsyncMock()

    with (
        patch("retrieval_service.main.create_embedding_provider", return_value=object()),
        patch(
            "retrieval_service.main.DocumentStore.connect",
            AsyncMock(return_value=document_store),
        ),
        patch(
            "retrieval_service.main.RetrievalCache.from_url",
            return_value=retrieval_cache,
        ) as from_url,
        TestClient(app),
    ):
        from_url.assert_called_once_with("redis://cache:6379/0", 120)
        assert app.state.retrieval_cache is retrieval_cache

    retrieval_cache.close.assert_awaited_once()
    document_store.close.assert_awaited_once()
    assert app.state.retrieval_cache is None
