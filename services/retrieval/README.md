# Retrieval service

The retrieval service owns evaluation documents and exposes two internal APIs:

- `POST /documents` idempotently creates or replaces up to 100 documents by ID.
- `POST /search` returns citation-ready evidence using a query and an optional
  `topK` value from 1 through 10.

## Storage modes

When `DATABASE_URL` is configured, startup creates the `retrieval_documents`
table and seeds the version-controlled evaluation corpus only if the table is
empty. Ingestion and subsequent searches then use PostgreSQL. The application
accepts both normal PostgreSQL URLs and `postgresql+asyncpg://` URLs.

When `DATABASE_URL` is absent, search uses the corpus in
`src/retrieval_service/corpus.py` directly. This lightweight mode is useful for
unit tests and standalone development; ingestion returns `503` because it
cannot persist documents.

In both modes, ranking is deterministic query-term overlap with extra weight
for title and tag matches. Storage and ranking are kept separate so pgvector
embeddings can replace the lexical ranker without changing the agent-facing
response.

## Local workflow

Start the service and its dependencies from the repository root:

```bash
docker compose -f infra/compose/compose.yaml up --build postgres redis retrieval
```

Check storage readiness:

```bash
curl http://localhost:8002/ready
```

Ingest a document. Sending the same ID again replaces its searchable fields:

```bash
curl -X POST http://localhost:8002/documents \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: local-ingestion-1' \
  -d '{
    "documents": [{
      "id": "local-load-test",
      "title": "Local load test",
      "source": "evaluation/performance/local.json",
      "content": "The local run sustained 24 requests per second.",
      "tags": ["performance", "throughput"]
    }]
  }'
```

Search the persisted corpus:

```bash
curl -X POST http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"local throughput", "topK":3}'
```

`GET /health` is the process liveness check. `GET /ready` additionally verifies
PostgreSQL when persistent storage is enabled.

## Current boundary

This milestone persists whole evaluation documents and ranks the stored set in
the service process. Document chunking, embeddings, pgvector nearest-neighbor
queries, and Redis caching remain follow-up work.
