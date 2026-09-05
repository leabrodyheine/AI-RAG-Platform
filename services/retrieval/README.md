# Retrieval service

The retrieval service exposes `POST /search` for ranked evaluation evidence.
The request accepts a query and an optional `topK` value from 1 through 10. The
response contains citation-ready results with stable IDs, source paths,
excerpts, and relevance scores.

The current implementation searches the small, version-controlled evaluation
corpus in `src/retrieval_service/corpus.py`. Ranking is deterministic and uses
query-term overlap with additional weight for title and tag matches. This keeps
the first retrieval slice reproducible and operational without external model
downloads.

The service contract is intentionally independent of the search implementation.
PostgreSQL ingestion, embeddings, pgvector search, and Redis caching can replace
the in-process corpus incrementally without changing the agent-facing response.
