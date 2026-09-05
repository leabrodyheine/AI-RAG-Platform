from pathlib import Path

from retrieval_service.database import create_chunks_table_sql
from retrieval_service.embeddings import SEMANTIC_EMBEDDING_DIMENSIONS

MIGRATIONS = Path(__file__).parents[1] / "migrations"


def test_vector_migration_enables_pgvector_and_creates_chunk_index() -> None:
    migration = (MIGRATIONS / "0002_create_retrieval_chunks.sql").read_text()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert "embedding vector(256) NOT NULL" in migration
    assert "REFERENCES retrieval_documents(id) ON DELETE CASCADE" in migration
    assert "USING hnsw (embedding vector_cosine_ops)" in migration


def test_semantic_migration_versions_384_dimension_embeddings() -> None:
    migration = (MIGRATIONS / "0003_version_semantic_embeddings.sql").read_text()

    assert "DROP TABLE IF EXISTS retrieval_chunks" in migration
    assert "embedding vector(384) NOT NULL" in migration
    assert "embedding_model TEXT NOT NULL" in migration
    assert (
        f"embedding vector({SEMANTIC_EMBEDDING_DIMENSIONS}) NOT NULL"
        in create_chunks_table_sql(SEMANTIC_EMBEDDING_DIMENSIONS)
    )
