DROP TABLE IF EXISTS retrieval_chunks;

CREATE TABLE retrieval_chunks (
    document_id TEXT NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    content TEXT NOT NULL CHECK (char_length(content) > 0),
    embedding vector(384) NOT NULL,
    embedding_model TEXT NOT NULL,
    PRIMARY KEY (document_id, chunk_index)
);

CREATE INDEX retrieval_chunks_embedding_hnsw_idx
ON retrieval_chunks USING hnsw (embedding vector_cosine_ops);
