from collections.abc import Sequence

import asyncpg

from retrieval_service.corpus import EVALUATION_DOCUMENTS, EvaluationDocument
from retrieval_service.embeddings import EMBEDDING_DIMENSIONS, embed_text
from retrieval_service.ingestion import DocumentChunk, chunk_document
from retrieval_service.schemas import DocumentInput

CREATE_VECTOR_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"

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

CREATE_CHUNKS_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    document_id TEXT NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (char_length(content) > 0),
    embedding vector({EMBEDDING_DIMENSIONS}) NOT NULL,
    PRIMARY KEY (document_id, chunk_index)
)
"""

CREATE_CHUNKS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_hnsw_idx
ON retrieval_chunks USING hnsw (embedding vector_cosine_ops)
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

LIST_UNINDEXED_DOCUMENTS_SQL = """
SELECT id, title, source, content, tags
FROM retrieval_documents AS document
WHERE NOT EXISTS (
    SELECT 1 FROM retrieval_chunks AS chunk WHERE chunk.document_id = document.id
)
ORDER BY id
"""

DELETE_DOCUMENT_CHUNKS_SQL = """
DELETE FROM retrieval_chunks
WHERE document_id = ANY($1::text[])
"""

INSERT_CHUNK_SQL = """
INSERT INTO retrieval_chunks (document_id, chunk_index, content, embedding)
VALUES ($1, $2, $3, $4::vector)
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
                await connection.execute(CREATE_VECTOR_EXTENSION_SQL)
                await connection.execute(CREATE_DOCUMENTS_TABLE_SQL)
                await connection.execute(CREATE_CHUNKS_TABLE_SQL)
                await connection.execute(CREATE_CHUNKS_INDEX_SQL)
                document_count = await connection.fetchval(
                    "SELECT COUNT(*) FROM retrieval_documents"
                )
                if document_count == 0:
                    await _upsert_and_index(connection, EVALUATION_DOCUMENTS)
                else:
                    unindexed_rows = await connection.fetch(LIST_UNINDEXED_DOCUMENTS_SQL)
                    if unindexed_rows:
                        await _index_documents(
                            connection,
                            tuple(_row_to_document(row) for row in unindexed_rows),
                        )

    async def upsert_documents(self, documents: Sequence[DocumentInput]) -> int:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await _upsert_and_index(connection, documents)
        return len(documents)

    async def list_documents(self) -> tuple[EvaluationDocument, ...]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(LIST_DOCUMENTS_SQL)
        return tuple(_row_to_document(row) for row in rows)

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


async def _upsert_and_index(
    connection: asyncpg.Connection,
    documents: Sequence[DocumentInput | EvaluationDocument],
) -> None:
    await connection.executemany(
        UPSERT_DOCUMENT_SQL,
        [_document_values(document) for document in documents],
    )
    await _index_documents(connection, documents)


async def _index_documents(
    connection: asyncpg.Connection,
    documents: Sequence[DocumentInput | EvaluationDocument],
) -> None:
    await connection.execute(
        DELETE_DOCUMENT_CHUNKS_SQL,
        [document.id for document in documents],
    )
    chunk_rows = [
        _chunk_values(document, chunk)
        for document in documents
        for chunk in chunk_document(document)
    ]
    await connection.executemany(INSERT_CHUNK_SQL, chunk_rows)


def _row_to_document(row: asyncpg.Record) -> EvaluationDocument:
    return EvaluationDocument(
        id=row["id"],
        title=row["title"],
        source=row["source"],
        content=row["content"],
        tags=tuple(row["tags"]),
    )


def _chunk_values(
    document: DocumentInput | EvaluationDocument,
    chunk: DocumentChunk,
) -> tuple[str, int, str, str]:
    embedding_input = "\n".join((document.title, " ".join(document.tags), chunk.content))
    embedding = embed_text(embedding_input)
    vector_literal = "[" + ",".join(f"{value:.12g}" for value in embedding) + "]"
    return document.id, chunk.index, chunk.content, vector_literal
