CREATE TABLE IF NOT EXISTS retrieval_state (
    key TEXT PRIMARY KEY,
    value BIGINT NOT NULL CHECK (value >= 1)
);

INSERT INTO retrieval_state (key, value)
VALUES ('corpus_generation', 1)
ON CONFLICT (key) DO NOTHING;
