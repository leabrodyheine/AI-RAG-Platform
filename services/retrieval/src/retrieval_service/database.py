import asyncio
from collections.abc import Sequence

import asyncpg

from retrieval_service.corpus import EVALUATION_DOCUMENTS, EvaluationDocument
from retrieval_service.embeddings import EmbeddingProvider, FeatureHashEmbeddingProvider
from retrieval_service.ingestion import DocumentChunk, chunk_document
from retrieval_service.schemas import DocumentInput
from retrieval_service.search import RankedDocument

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

CREATE_RETRIEVAL_STATE_SQL = """
CREATE TABLE IF NOT EXISTS retrieval_state (
    key TEXT PRIMARY KEY,
    value BIGINT NOT NULL CHECK (value >= 1)
)
"""

INITIALIZE_CORPUS_GENERATION_SQL = """
INSERT INTO retrieval_state (key, value)
VALUES ('corpus_generation', 1)
ON CONFLICT (key) DO NOTHING
"""

READ_CORPUS_GENERATION_SQL = """
SELECT value FROM retrieval_state WHERE key = 'corpus_generation'
"""

INCREMENT_CORPUS_GENERATION_SQL = """
UPDATE retrieval_state
SET value = value + 1
WHERE key = 'corpus_generation'
RETURNING value
"""

def create_chunks_table_sql(dimensions: int) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    document_id TEXT NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (char_length(content) > 0),
    embedding vector({dimensions}) NOT NULL,
    embedding_model TEXT,
    PRIMARY KEY (document_id, chunk_index)
)
"""


def reset_chunks_for_dimension_sql(dimensions: int) -> str:
    return f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_attribute AS attribute
        JOIN pg_class AS relation ON relation.oid = attribute.attrelid
        WHERE relation.relname = 'retrieval_chunks'
          AND attribute.attname = 'embedding'
          AND format_type(attribute.atttypid, attribute.atttypmod) <> 'vector({dimensions})'
    ) THEN
        DROP TABLE retrieval_chunks;
    END IF;
END
$$
"""


CREATE_CHUNKS_TABLE_SQL = create_chunks_table_sql(
    FeatureHashEmbeddingProvider.dimensions
)

ADD_EMBEDDING_MODEL_COLUMN_SQL = """
ALTER TABLE retrieval_chunks
ADD COLUMN IF NOT EXISTS embedding_model TEXT
"""

REQUIRE_EMBEDDING_MODEL_SQL = """
ALTER TABLE retrieval_chunks
ALTER COLUMN embedding_model SET NOT NULL
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
    SELECT 1
    FROM retrieval_chunks AS chunk
    WHERE chunk.document_id = document.id AND chunk.embedding_model = $1
)
ORDER BY id
"""

DELETE_DOCUMENT_CHUNKS_SQL = """
DELETE FROM retrieval_chunks
WHERE document_id = ANY($1::text[])
"""

INSERT_CHUNK_SQL = """
INSERT INTO retrieval_chunks (document_id, chunk_index, content, embedding, embedding_model)
VALUES ($1, $2, $3, $4::vector, $5)
"""

VECTOR_SEARCH_SQL = """
WITH chunk_scores AS (
    SELECT
        document.id,
        document.title,
        document.source,
        document.tags,
        chunk.content AS excerpt,
        LEAST(1.0, GREATEST(0.0, 1 - (chunk.embedding <=> $1::vector))) AS relevance
    FROM retrieval_chunks AS chunk
    JOIN retrieval_documents AS document ON document.id = chunk.document_id
    WHERE chunk.embedding_model = $3
),
ranked_chunks AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY id ORDER BY relevance DESC, excerpt
    ) AS chunk_rank
    FROM chunk_scores
)
SELECT id, title, source, tags, excerpt, relevance
FROM ranked_chunks
WHERE chunk_rank = 1 AND relevance > 0
ORDER BY relevance DESC, id
LIMIT $2
"""


class DocumentStore:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._pool = pool
        self._embedding_provider = embedding_provider or FeatureHashEmbeddingProvider()
        if not 1 <= self._embedding_provider.dimensions <= 2_000:
            raise ValueError("embedding dimensions must be between 1 and 2000")

    @property
    def embedding_version(self) -> str:
        return self._embedding_provider.version

    @classmethod
    async def connect(
        cls,
        database_url: str,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "DocumentStore":
        pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5)
        store = cls(pool, embedding_provider)
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
                await connection.execute(CREATE_RETRIEVAL_STATE_SQL)
                await connection.execute(INITIALIZE_CORPUS_GENERATION_SQL)
                await connection.execute(
                    reset_chunks_for_dimension_sql(self._embedding_provider.dimensions)
                )
                await connection.execute(
                    create_chunks_table_sql(self._embedding_provider.dimensions)
                )
                await connection.execute(ADD_EMBEDDING_MODEL_COLUMN_SQL)
                await connection.execute(CREATE_CHUNKS_INDEX_SQL)
                document_count = await connection.fetchval(
                    "SELECT COUNT(*) FROM retrieval_documents"
                )
                if document_count == 0:
                    await _upsert_and_index(
                        connection,
                        EVALUATION_DOCUMENTS,
                        self._embedding_provider,
                    )
                else:
                    unindexed_rows = await connection.fetch(
                        LIST_UNINDEXED_DOCUMENTS_SQL,
                        self._embedding_provider.version,
                    )
                    if unindexed_rows:
                        await _index_documents(
                            connection,
                            tuple(_row_to_document(row) for row in unindexed_rows),
                            self._embedding_provider,
                        )
                await connection.execute(REQUIRE_EMBEDDING_MODEL_SQL)

    async def upsert_documents(self, documents: Sequence[DocumentInput]) -> int:
        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await _upsert_and_index(connection, documents, self._embedding_provider)
                await connection.fetchval(INCREMENT_CORPUS_GENERATION_SQL)
        return len(documents)

    async def corpus_generation(self) -> int:
        async with self._pool.acquire() as connection:
            generation = await connection.fetchval(READ_CORPUS_GENERATION_SQL)
        return int(generation)

    async def list_documents(self) -> tuple[EvaluationDocument, ...]:
        async with self._pool.acquire() as connection:
            rows = await connection.fetch(LIST_DOCUMENTS_SQL)
        return tuple(_row_to_document(row) for row in rows)

    async def search(self, query: str, top_k: int) -> list[RankedDocument]:
        query_embedding = await asyncio.to_thread(self._embedding_provider.embed_query, query)
        if not any(query_embedding):
            return []
        if len(query_embedding) != self._embedding_provider.dimensions:
            raise RuntimeError("embedding provider returned an unexpected vector size")

        async with self._pool.acquire() as connection:
            rows = await connection.fetch(
                VECTOR_SEARCH_SQL,
                _vector_literal(query_embedding),
                top_k,
                self._embedding_provider.version,
            )
        return [
            RankedDocument(
                document=EvaluationDocument(
                    id=row["id"],
                    title=row["title"],
                    source=row["source"],
                    content=row["excerpt"],
                    tags=tuple(row["tags"]),
                ),
                relevance=round(float(row["relevance"]), 4),
            )
            for row in rows
        ]

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
    embedding_provider: EmbeddingProvider,
) -> None:
    await connection.executemany(
        UPSERT_DOCUMENT_SQL,
        [_document_values(document) for document in documents],
    )
    await _index_documents(connection, documents, embedding_provider)


async def _index_documents(
    connection: asyncpg.Connection,
    documents: Sequence[DocumentInput | EvaluationDocument],
    embedding_provider: EmbeddingProvider,
) -> None:
    await connection.execute(
        DELETE_DOCUMENT_CHUNKS_SQL,
        [document.id for document in documents],
    )
    chunks = [
        (document, chunk)
        for document in documents
        for chunk in chunk_document(document)
    ]
    passage_inputs = [_embedding_input(document, chunk) for document, chunk in chunks]
    embeddings = await asyncio.to_thread(
        embedding_provider.embed_passages,
        passage_inputs,
    )
    if len(embeddings) != len(chunks):
        raise RuntimeError("embedding provider returned an unexpected number of vectors")
    if any(len(embedding) != embedding_provider.dimensions for embedding in embeddings):
        raise RuntimeError("embedding provider returned an unexpected vector size")
    chunk_rows = [
        _chunk_values(document, chunk, embedding, embedding_provider.version)
        for (document, chunk), embedding in zip(chunks, embeddings, strict=True)
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
    embedding: tuple[float, ...],
    embedding_model: str,
) -> tuple[str, int, str, str, str]:
    return (
        document.id,
        chunk.index,
        chunk.content,
        _vector_literal(embedding),
        embedding_model,
    )


def _embedding_input(
    document: DocumentInput | EvaluationDocument,
    chunk: DocumentChunk,
) -> str:
    return "\n".join((document.title, " ".join(document.tags), chunk.content))


def _vector_literal(embedding: tuple[float, ...]) -> str:
    return "[" + ",".join(f"{value:.12g}" for value in embedding) + "]"
