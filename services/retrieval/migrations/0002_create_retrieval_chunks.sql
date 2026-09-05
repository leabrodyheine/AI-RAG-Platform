CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    document_id TEXT NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (char_length(content) > 0),
    embedding vector(256) NOT NULL,
    PRIMARY KEY (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS retrieval_chunks_embedding_hnsw_idx
ON retrieval_chunks USING hnsw (embedding vector_cosine_ops);
