from pathlib import Path

MIGRATIONS = Path(__file__).parents[1] / "migrations"


def test_vector_migration_enables_pgvector_and_creates_chunk_index() -> None:
    migration = (MIGRATIONS / "0002_create_retrieval_chunks.sql").read_text()

    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert "embedding vector(256) NOT NULL" in migration
    assert "REFERENCES retrieval_documents(id) ON DELETE CASCADE" in migration
    assert "USING hnsw (embedding vector_cosine_ops)" in migration
