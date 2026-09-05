# Retrieval service

The retrieval service owns evaluation documents and exposes two internal APIs:

- `POST /documents` idempotently creates or replaces up to 100 documents by ID.
- `POST /search` returns citation-ready evidence using a query and an optional
  `topK` value from 1 through 10.

## Storage modes

When `DATABASE_URL` is configured, startup enables pgvector, creates the
document and chunk tables, and seeds the version-controlled evaluation corpus
only if the document table is empty. Existing documents without chunks are
backfilled automatically. The application accepts both normal PostgreSQL URLs
and `postgresql+asyncpg://` URLs.

When `DATABASE_URL` is absent, search uses the corpus in
`src/retrieval_service/corpus.py` directly. This lightweight mode is useful for
unit tests and standalone development; ingestion returns `503` because it
cannot persist documents.

Persistent ingestion splits content into overlapping 120-word chunks. Each
chunk is embedded together with its document title and tags, then the document
and its complete replacement chunk set are written in one transaction.
Re-ingesting an ID therefore cannot leave stale chunks behind.

Persistent search uses pgvector cosine distance and returns the strongest chunk
from each matching document. The in-memory mode retains deterministic
query-term ranking. Both modes preserve the same stable document IDs and
citation response shape.

The local embedding function uses normalized 256-dimensional feature hashing.
It is deterministic, fast, and requires no network or model download, making it
useful for validating ingestion, pgvector indexing, and service behavior. It is
not a semantic language model and should not be used as the final quality
baseline.

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

This milestone implements chunking, local embeddings, pgvector persistence, and
nearest-neighbor retrieval. The next retrieval-quality step is replacing the
feature-hashed embedder with a versioned production embedding model and
re-indexing the corpus. Redis result caching remains separate follow-up work
for the performance evaluation slice.
