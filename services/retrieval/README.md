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

When both PostgreSQL and `REDIS_URL` are configured, persistent searches cache
their ranked results. Keys hash the normalized query together with `topK`, the
embedding model version, and an authoritative PostgreSQL corpus generation.
Successful ingestion increments that generation in the document transaction,
making every older cache entry unreachable without scanning or flushing Redis.

Redis is fail-open: connection failures bypass caching and continue through
semantic embedding and pgvector. Malformed entries are treated as misses and
removed when possible. Empty search results are cached normally.

Every successful search reports one of these headers:

- `X-Cache: HIT` — returned directly from Redis.
- `X-Cache: MISS` — retrieved from pgvector and written to Redis.
- `X-Cache: BYPASS` — Redis is disabled, unavailable, or unnecessary in
  database-free mode.

Persistent mode defaults to FastEmbed with `BAAI/bge-small-en-v1.5`. It uses
the model's retrieval-specific passage encoder during ingestion and query
encoder during search, producing 384-dimensional semantic vectors. CPU-bound
model work runs outside FastAPI's event loop.

Every chunk records `EMBEDDING_MODEL_VERSION`. At startup, documents without
chunks for the configured version are re-indexed. A vector-dimension change
rebuilds only the derived chunk table; source documents remain intact. Change
the version whenever model weights or embedding behavior changes.

The first semantic startup downloads approximately 67 MB of model artifacts.
Compose persists them in the `embedding-cache` volume so later starts reuse the
same files.

For tests or offline development, select deterministic feature hashing:

```bash
EMBEDDING_PROVIDER=feature-hash \
DATABASE_URL=postgresql://rag_platform:local-development-only@localhost/rag_platform \
uvicorn retrieval_service.main:app --port 8002
```

Feature hashing exercises the vector pipeline but is not a semantic quality
baseline. Database-free mode still uses the lexical in-memory search path and
does not initialize either embedding provider.

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

Use `-i` to compare cache behavior. The first identical request should report a
miss and the second a hit until the configured TTL expires:

```bash
curl -i -X POST http://localhost:8002/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"retrieval latency", "topK":3}'
```

The local default is `RETRIEVAL_CACHE_TTL_SECONDS=60`. When running the service
directly, leave `REDIS_URL` unset to measure the uncached path without changing
retrieval results.

`GET /health` is the process liveness check. `GET /ready` additionally verifies
PostgreSQL when persistent storage is enabled.

## Current boundary

This milestone provides versioned semantic embeddings and automatic safe
re-indexing plus generation-safe Redis result caching. Model evaluation and
threshold tuning still need a representative retrieval dataset. The next
vertical slice is connecting the agent to real inference so evidence is
synthesized by a model instead of the deterministic development answer builder.
