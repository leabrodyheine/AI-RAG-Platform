from contextlib import AbstractAsyncContextManager
from unittest.mock import AsyncMock, patch

import pytest
from retrieval_service.corpus import EVALUATION_DOCUMENTS
from retrieval_service.database import (
    ADD_EMBEDDING_MODEL_COLUMN_SQL,
    CREATE_CHUNKS_INDEX_SQL,
    CREATE_DOCUMENTS_TABLE_SQL,
    CREATE_RETRIEVAL_STATE_SQL,
    CREATE_VECTOR_EXTENSION_SQL,
    DELETE_DOCUMENT_CHUNKS_SQL,
    INCREMENT_CORPUS_GENERATION_SQL,
    INITIALIZE_CORPUS_GENERATION_SQL,
    READ_CORPUS_GENERATION_SQL,
    VECTOR_SEARCH_SQL,
    DocumentStore,
    create_chunks_table_sql,
    reset_chunks_for_dimension_sql,
)
from retrieval_service.embeddings import FeatureHashEmbeddingProvider
from retrieval_service.schemas import DocumentInput


class AsyncContext(AbstractAsyncContextManager):
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args) -> None:
        return None


class FakeConnection:
    def __init__(self, *, count: int = 0, rows: list[dict] | None = None) -> None:
        self.execute = AsyncMock()
        self.executemany = AsyncMock()
        self.fetchval = AsyncMock(side_effect=[count])
        self.fetch = AsyncMock(return_value=rows or [])

    def transaction(self) -> AsyncContext:
        return AsyncContext(None)


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.close = AsyncMock()

    def acquire(self) -> AsyncContext:
        return AsyncContext(self.connection)


@pytest.mark.anyio
async def test_initialize_creates_and_seeds_an_empty_document_table() -> None:
    connection = FakeConnection(count=0)
    store = DocumentStore(FakePool(connection))

    await store.initialize()

    schema_statements = [call.args[0] for call in connection.execute.await_args_list[:8]]
    assert schema_statements == [
        CREATE_VECTOR_EXTENSION_SQL,
        CREATE_DOCUMENTS_TABLE_SQL,
        CREATE_RETRIEVAL_STATE_SQL,
        INITIALIZE_CORPUS_GENERATION_SQL,
        reset_chunks_for_dimension_sql(FeatureHashEmbeddingProvider.dimensions),
        create_chunks_table_sql(FeatureHashEmbeddingProvider.dimensions),
        ADD_EMBEDDING_MODEL_COLUMN_SQL,
        CREATE_CHUNKS_INDEX_SQL,
    ]
    seeded_rows = connection.executemany.await_args_list[0].args[1]
    assert len(seeded_rows) == len(EVALUATION_DOCUMENTS)
    assert seeded_rows[0][0] == EVALUATION_DOCUMENTS[0].id
    seeded_chunks = connection.executemany.await_args_list[1].args[1]
    assert len(seeded_chunks) == len(EVALUATION_DOCUMENTS)
    assert seeded_chunks[0][0] == EVALUATION_DOCUMENTS[0].id
    assert seeded_chunks[0][3].startswith("[")
    assert seeded_chunks[0][4] == "feature-hash-v1"


@pytest.mark.anyio
async def test_initialize_does_not_replace_existing_documents() -> None:
    connection = FakeConnection(count=2)
    store = DocumentStore(FakePool(connection))

    await store.initialize()

    connection.executemany.assert_not_awaited()


@pytest.mark.anyio
async def test_initialize_backfills_documents_created_before_vector_migration() -> None:
    connection = FakeConnection(
        count=2,
        rows=[
            {
                "id": "legacy-result",
                "title": "Legacy result",
                "source": "evaluation/legacy.json",
                "content": "Legacy retrieval latency was 140 ms.",
                "tags": ["retrieval"],
            }
        ],
    )
    store = DocumentStore(FakePool(connection))

    await store.initialize()

    indexed_chunks = connection.executemany.await_args.args[1]
    assert indexed_chunks[0][0] == "legacy-result"


@pytest.mark.anyio
async def test_upsert_documents_returns_the_written_count() -> None:
    connection = FakeConnection()
    store = DocumentStore(FakePool(connection))
    document = DocumentInput(
        id="result-2",
        title="Result two",
        source="evaluation/result-2.json",
        content="p95 latency was 95 ms.",
        tags=("latency",),
    )

    count = await store.upsert_documents([document])

    assert count == 1
    assert connection.executemany.await_args_list[0].args[1] == [
        (
            "result-2",
            "Result two",
            "evaluation/result-2.json",
            "p95 latency was 95 ms.",
            ["latency"],
        )
    ]
    connection.execute.assert_awaited_once_with(DELETE_DOCUMENT_CHUNKS_SQL, ["result-2"])
    indexed_chunks = connection.executemany.await_args_list[1].args[1]
    assert indexed_chunks[0][:3] == (
        "result-2",
        0,
        "p95 latency was 95 ms.",
    )
    assert len(indexed_chunks[0][3].strip("[]").split(",")) == 256
    assert indexed_chunks[0][4] == "feature-hash-v1"
    connection.fetchval.assert_awaited_once_with(INCREMENT_CORPUS_GENERATION_SQL)


@pytest.mark.anyio
async def test_list_documents_maps_database_rows() -> None:
    connection = FakeConnection(
        rows=[
            {
                "id": "result-3",
                "title": "Result three",
                "source": "evaluation/result-3.json",
                "content": "Recall was 90%.",
                "tags": ["quality", "recall"],
            }
        ]
    )
    store = DocumentStore(FakePool(connection))

    documents = await store.list_documents()

    assert documents[0].id == "result-3"
    assert documents[0].tags == ("quality", "recall")


@pytest.mark.anyio
async def test_corpus_generation_is_read_from_postgres() -> None:
    connection = FakeConnection(count=7)
    store = DocumentStore(FakePool(connection))

    assert await store.corpus_generation() == 7
    connection.fetchval.assert_awaited_once_with(READ_CORPUS_GENERATION_SQL)


@pytest.mark.anyio
async def test_search_maps_the_best_vector_chunk_per_document() -> None:
    connection = FakeConnection(
        rows=[
            {
                "id": "result-4",
                "title": "Result four",
                "source": "evaluation/result-4.json",
                "excerpt": "The most relevant chunk.",
                "tags": ["retrieval"],
                "relevance": 0.87654,
            }
        ]
    )
    store = DocumentStore(FakePool(connection))

    results = await store.search("retrieval latency", 3)

    assert results[0].document.content == "The most relevant chunk."
    assert results[0].relevance == 0.8765
    query_args = connection.fetch.await_args.args
    assert query_args[0] == VECTOR_SEARCH_SQL
    assert "chunk.embedding <=> $1::vector" in VECTOR_SEARCH_SQL
    assert "PARTITION BY id ORDER BY relevance DESC" in VECTOR_SEARCH_SQL
    assert len(query_args[1].strip("[]").split(",")) == 256
    assert query_args[2] == 3
    assert query_args[3] == "feature-hash-v1"


@pytest.mark.anyio
async def test_search_skips_database_for_an_empty_embedding() -> None:
    connection = FakeConnection()
    store = DocumentStore(FakePool(connection))

    assert await store.search("!!!", 3) == []
    connection.fetch.assert_not_awaited()


@pytest.mark.anyio
async def test_store_batches_passages_through_its_configured_provider() -> None:
    class RecordingProvider:
        dimensions = 3
        version = "semantic-model@v2"

        def __init__(self) -> None:
            self.passages = []

        def embed_query(self, _text: str) -> tuple[float, ...]:
            return (1.0, 0.0, 0.0)

        def embed_passages(self, texts) -> list[tuple[float, ...]]:
            self.passages = list(texts)
            return [(1.0, 0.0, 0.0) for _text in texts]

    connection = FakeConnection()
    provider = RecordingProvider()
    store = DocumentStore(FakePool(connection), provider)
    document = DocumentInput(
        id="semantic-result",
        title="Semantic result",
        source="evaluation/semantic.json",
        content="The request delay was reduced.",
        tags=("latency",),
    )

    await store.upsert_documents([document])

    assert provider.passages == [
        "Semantic result\nlatency\nThe request delay was reduced."
    ]
    indexed_chunk = connection.executemany.await_args_list[1].args[1][0]
    assert indexed_chunk[3] == "[1,0,0]"
    assert indexed_chunk[4] == "semantic-model@v2"


@pytest.mark.anyio
async def test_store_runs_query_embedding_off_the_event_loop() -> None:
    connection = FakeConnection()
    store = DocumentStore(FakePool(connection))

    with patch(
        "retrieval_service.database.asyncio.to_thread",
        AsyncMock(side_effect=lambda function, *args: function(*args)),
    ) as to_thread:
        await store.search("retrieval latency", 2)

    to_thread.assert_awaited_once()


@pytest.mark.anyio
async def test_failed_ingestion_does_not_increment_corpus_generation() -> None:
    class FailedProvider:
        dimensions = 3
        version = "failed-model"

        def embed_query(self, _text: str) -> tuple[float, ...]:
            return (1.0, 0.0, 0.0)

        def embed_passages(self, _texts) -> list[tuple[float, ...]]:
            raise RuntimeError("embedding failed")

    connection = FakeConnection()
    store = DocumentStore(FakePool(connection), FailedProvider())
    document = DocumentInput(
        id="failed-result",
        title="Failed result",
        source="evaluation/failed.json",
        content="This document cannot be embedded.",
    )

    with pytest.raises(RuntimeError, match="embedding failed"):
        await store.upsert_documents([document])

    connection.fetchval.assert_not_awaited()


@pytest.mark.anyio
async def test_connect_closes_the_pool_when_initialization_fails() -> None:
    connection = FakeConnection()
    pool = FakePool(connection)

    with (
        patch("retrieval_service.database.asyncpg.create_pool", AsyncMock(return_value=pool)),
        patch.object(DocumentStore, "initialize", AsyncMock(side_effect=RuntimeError("failed"))),
        pytest.raises(RuntimeError, match="failed"),
    ):
        await DocumentStore.connect("postgresql://db/platform")

    pool.close.assert_awaited_once()


@pytest.mark.anyio
async def test_store_readiness_and_close_use_the_pool() -> None:
    connection = FakeConnection(count=1)
    pool = FakePool(connection)
    store = DocumentStore(pool)

    assert await store.is_ready() is True
    await store.close()

    pool.close.assert_awaited_once()
