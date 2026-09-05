# Database migrations

Ordered PostgreSQL schema changes live here. Migration `0001` defines the
document table used by the retrieval service. Migration `0002` enables pgvector
and adds embedded document chunks with a cosine-distance HNSW index. Service
startup applies the same idempotent definitions so local installations do not
need a separate migration command yet.

Migration `0003` rebuilds the derived chunk table for 384-dimensional semantic
embeddings and records the model version used for every vector. No source
documents are removed; service startup regenerates their chunks.

Introduce a dedicated migration tool before a schema change needs data
transformation or coordinated rollout behavior.
