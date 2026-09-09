# Final acceptance

This record maps every final-acceptance criterion to the code, configuration,
and checks that satisfy it. It was verified against the tree at commit
`19abc54` (the parent of the commit that adds this file); no source changed
between that verification and this document.

## Checks run

CPU-only macOS host, Python 3.11, Node 22, no GPU, no external database:

| Command | Result |
| --- | --- |
| `make lint` | `ruff` clean over `libs services tests scripts evaluation load-tests`; `tsc` clean — exit 0 |
| `make test` | Python **477 passed** (476 + 1 with the `psutil` load-test extra installed; the host-sampling telemetry test skips without it), 2 pre-existing unrelated deprecation warnings; web **10 passed** across 3 vitest files — exit 0 |
| `make k8s-validate` | `base`, `overlays/local`, `overlays/gpu` all render and pass the manifest invariants — `RESULT: PASS` |
| `make eval-quality-check` | quality metrics meet every threshold in `evaluation/quality/thresholds.json` — exit 0 |

A clean `git clone` + Quickstart run is recorded separately in the README
["Clean-clone verification"](../README.md#clean-clone-verification) section.

## Acceptance criteria

| Criterion | Evidence |
| --- | --- |
| The full request path works from the browser with real persisted documents. | `infra/compose/compose.yaml` wires the SPA (`:3000`) → gateway (`:8000`) → agent → retrieval → inference, with `pgvector/pgvector:pg16` + `redis:7-alpine` and a persistent `postgres-data` volume. `tests/end-to-end/test_rag_pipeline.py` drives the real gateway→agent→retrieval→inference chain over ASGI transports. README ["Primary demo"](../README.md#primary-demo) is the reviewer's step-by-step: ingest to `POST :8002/documents`, ask in the browser, get a grounded cited answer. |
| Internal services and data stores are not publicly exposed in the production-style deployment. | `infra/kubernetes/base/ingress.yaml` is the only external surface: `/` → `web`, `/api/*` → `api-gateway` (prefix stripped). Every other Service (`agent`, `retrieval`, `inference`, `postgres`, `redis`) is `ClusterIP` with no Ingress rule. `scripts/validate_k8s_manifests.py` asserts Service/Ingress reference resolution across all three kustomize targets. |
| Both target inference backends implement the same stable contract. | `services/inference/src/inference_service/backends/base.py` defines the `InferenceBackend` protocol; `vllm.py` and `triton.py` both implement it and the route returns `GenerationResponse` (`schemas.py`) regardless of backend. `contracts/openapi/inference-v1.openapi.json` + `tests/contracts/test_inference_openapi.py` pin the wire contract; `services/inference/tests/test_{vllm,triton}_backend.py` cover each adapter. |
| Agent behavior is bounded and failure-safe. | `services/agent/src/agent_service/workflow.py` runs a `max_steps=4` loop (`config.py`, env-overridable, validated finite/positive) gated on `min_relevance=0.3`. Retrieval and inference calls carry per-call timeouts. `tests/end-to-end/test_rag_pipeline.py` asserts inference outage → `503 agent_unavailable` and retrieval timeout → `504 agent_timeout`; `services/agent/tests/test_workflow_decisions.py` covers the loop's stop conditions. |
| Quality and performance evaluations are reproducible. | `make eval-quality` / `make eval-quality-check` run the deterministic offline harness (`evaluation/quality/`) against `evaluation/datasets/quality-core-v1.json` with enforced thresholds. Performance method and results are in `docs/performance-report.md` and `evaluation/performance/README.md`; the harness code is unit-tested under `evaluation/performance/tests/`. Reports write to gitignored `evaluation/reports/`. |
| Traces and metrics explain where request time is spent. | `libs/observability/` instruments every service identically: one `trace_id` + `request_id` across gateway/agent/retrieval/inference, inbound `http_server_request_duration_seconds`, outbound `http_client_request_duration_seconds{target}`, `retrieval_query_duration_seconds{path}`, `inference_generation_duration_seconds{backend,model}`. `docs/operations/observability.md` has the follow-one-request recipe and PromQL; `docs/performance-report.md` uses these signals to attribute the gateway hop at ~32% of chat latency. |
| Kubernetes configuration includes probes, resources, ingress, persistence, and GPU scheduling. | `infra/kubernetes/base/`: every Deployment has readiness/liveness probes and CPU/memory requests + limits; `ingress.yaml`; `postgres.yaml` binds a 2Gi `ReadWriteOnce` PVC with a `Recreate` strategy; `hpa.yaml` for the stateless services. `overlays/gpu/` schedules vLLM with `nvidia.com/gpu` and a node selector. `scripts/validate_k8s_manifests.py` enforces probes / resource requests / replica-count-xor-HPA / reference resolution on all three targets. |
| Automated checks pass from a clean checkout. | Recorded in README ["Clean-clone verification"](../README.md#clean-clone-verification): fresh `git clone` → `make install` / `make lint` / `make test` all exit 0. `.github/workflows/ci.yml` runs the same checks (Python, web, manifests) on every push to `main` and every PR. |
| No secrets, model artifacts, raw benchmark output, or generated junk are committed. | `.gitignore` excludes `.env*` (except `.env.example`), `data/`, `models/`, `evaluation/reports/*`, `evaluation/datasets/*` (except the README and `quality-core-v1.json`), `load-tests/results/*`, and generated Triton engines. `git ls-files` carries only source, config templates, and the small redistributable quality dataset. `infra/kubernetes/base/secret.yaml` holds throwaway local-dev values matching Compose, with an in-file note that real deployments inject a Secret from a manager. |
| README instructions and diagrams match the final implementation. | The architecture and request-flow diagrams are implementation-accurate Mermaid (commit `0592882`), embedded in the README and expanded in `docs/diagrams/`. The README Quickstart, Primary demo, Deployment table, and Observability sections describe the shipped ports, routes, backends, and error contract; the web evidence panel (`apps/web/src/features/chat/ChatWorkspace.tsx`) renders the `trace` steps with per-step `durationMs` and numbered citations exactly as the demo describes. |

## Completion gates

| Gate | Status |
| --- | --- |
| A reviewer can start the CPU-friendly stack and complete the primary demo from the README. | `docker compose up --build` from `infra/compose/` brings up the CPU-only stack (deterministic inference backend, `pgvector`, Redis, OTel/Prometheus/Grafana). README ["Primary demo"](../README.md#primary-demo) walks through ingest → browser question → grounded cited answer with a decision trace, plus a `curl`-only path and an offline `scripts/run_local_stack.py` variant that needs no database. |
| The GPU path is reproducible in a documented compatible environment. | `runtimes/vllm/` and `runtimes/triton/` pin the server configuration; `infra/kubernetes/overlays/gpu/` schedules vLLM on `nvidia.com/gpu` and switches the inference backend by configuration only. `scripts/smoke_vllm.py` / `scripts/smoke_triton.py` check a running server against the shared contract. The README ["Limitations"](../README.md#limitations) states plainly that the GPU path is configured and contract-tested but has not been run on GPU hardware in this project. |
| All committed documentation describes the implemented system rather than proposed behavior. | The two "PROPOSED DESIGN" images were removed in commit `0592882`. A repository-wide search for proposed / future / TODO / "to be implemented" language in tracked docs and code returns nothing. Every README and `docs/` claim above is backed by code or configuration in the same tree. |
