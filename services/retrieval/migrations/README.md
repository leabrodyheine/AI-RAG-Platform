# Database migrations

Ordered PostgreSQL schema changes live here. Migration `0001` defines the
document table used by the retrieval service. Service startup applies the same
idempotent table definition so local installations do not need a separate
migration command yet.

Introduce a dedicated migration tool before a schema change needs data
transformation or coordinated rollout behavior.
