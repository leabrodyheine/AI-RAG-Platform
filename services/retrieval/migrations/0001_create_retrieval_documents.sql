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
);
