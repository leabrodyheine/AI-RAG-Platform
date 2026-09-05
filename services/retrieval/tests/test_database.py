from contextlib import AbstractAsyncContextManager
from unittest.mock import AsyncMock, patch

import pytest
from retrieval_service.corpus import EVALUATION_DOCUMENTS
from retrieval_service.database import DocumentStore
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

    connection.execute.assert_awaited_once()
    seeded_rows = connection.executemany.await_args.args[1]
    assert len(seeded_rows) == len(EVALUATION_DOCUMENTS)
    assert seeded_rows[0][0] == EVALUATION_DOCUMENTS[0].id


@pytest.mark.anyio
async def test_initialize_does_not_replace_existing_documents() -> None:
    connection = FakeConnection(count=2)
    store = DocumentStore(FakePool(connection))

    await store.initialize()

    connection.executemany.assert_not_awaited()


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
    assert connection.executemany.await_args.args[1] == [
        (
            "result-2",
            "Result two",
            "evaluation/result-2.json",
            "p95 latency was 95 ms.",
            ["latency"],
        )
    ]


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
