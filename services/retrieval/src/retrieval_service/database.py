from collections.abc import Sequence

import asyncpg

from retrieval_service.corpus import EVALUATION_DOCUMENTS, EvaluationDocument
from retrieval_service.schemas import DocumentInput

CREATE_DOCUMENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retrieval_documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT retrieval_documents_id_length CHECK (char_length(id) BETWEEN 1 AND 128),
    CONSTRAINT retrieval_documents_title_length CHECK (char_length(title) BETWEEN 1 AND 200),
    CONSTRAINT retrieval_documents_source_length CHECK (char_length(source) BETWEEN 1 AND 500),
    CONSTRAINT retrieval_documents_content_length CHECK (char_length(content) BETWEEN 1 AND 20000),
    CONSTRAINT retrieval_documents_tags_count CHECK (cardinality(tags) <= 20)
)
"""

UPSERT_DOCUMENT_SQL = """
INSERT INTO retrieval_documents (id, title, source, content, tags)
VALUES ($1, $2, $3, $4, $5)
ON CONFLICT (id) DO UPDATE SET
    title = EXCLUDED.title,
    source = EXCLUDED.source,
    content = EXCLUDED.content,
    tags = EXCLUDED.tags,
    updated_at = NOW()
"""

LIST_DOCUMENTS_SQL = """
SELECT id, title, source, content, tags
FROM retrieval_documents
ORDER BY id
"""


class DocumentStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, database_url: str) -> "DocumentStore":
        pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5)
        store = cls(pool)
        try:
            await store.initialize()
        except Exception:
            await pool.close()
            raise
        return store

    async def initialize(self) -> None:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(CREATE_DOCUMENTS_TABLE_SQL)
                document_count = await connection.fetchval(
                    "SELECT COUNT(*) FROM retrieval_documents"
                )
                if document_count == 0:
                    await connection.executemany(
                        UPSERT_DOCUMENT_SQL,
                        [_document_values(document) for document in EVALUATION_DOCUMENTS],
                    )

    async def upsert_documents(self, documents: Sequence[DocumentInput]) -> int:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.executemany(
                    UPSERT_DOCUMENT_SQL,
                    [_document_values(document) for document in documents],
                )
        return len(documents)

    async def list_documents(self) -> tuple[EvaluationDocument, ...]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(LIST_DOCUMENTS_SQL)
        return tuple(
            EvaluationDocument(
                id=row["id"],
                title=row["title"],
                source=row["source"],
                content=row["content"],
                tags=tuple(row["tags"]),
            )
            for row in rows
        )

    async def is_ready(self) -> bool:
        async with self._pool.acquire() as connection:
            return await connection.fetchval("SELECT 1") == 1

    async def close(self) -> None:
        await self._pool.close()


def _document_values(
    document: DocumentInput | EvaluationDocument,
) -> tuple[str, str, str, str, list[str]]:
    return (
        document.id,
        document.title,
        document.source,
        document.content,
        list(document.tags),
    )
