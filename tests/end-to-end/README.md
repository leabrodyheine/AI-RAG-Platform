# End-to-end tests

Full browser-to-model workflows exercised over the four services wired together.

`test_rag_pipeline.py` runs the real gateway -> agent -> retrieval -> inference
chain over in-process ASGI transports (no network, no Postgres, no Redis) and
covers:

- **ingestion** — a document posted to `retrieval /documents` becomes retrievable
  on the next chat request;
- **chat and citations** — the grounded answer quotes the ingested evidence and
  cites it as `[1]`, with the expected `Plan -> Retrieve -> Assess -> Generate`
  trace;
- **caching** — a repeated query returns `X-Cache: HIT` and is answered without
  re-searching the store;
- **failure handling** — an inference outage degrades to a `503`
  (`agent_unavailable`) and a retrieval timeout to a `504` (`agent_timeout`),
  both echoing the request id, rather than hanging or returning a `500`.

The document store and cache are in-memory fakes injected through FastAPI
dependency overrides; the pgvector and Redis code paths have their own unit tests
under `services/retrieval/tests`.

Browser-to-model workflows against a deployed local stack (kind/Minikube) belong
here too; `scripts/smoke_k8s_deployment.py` is the post-`kubectl apply` check.
