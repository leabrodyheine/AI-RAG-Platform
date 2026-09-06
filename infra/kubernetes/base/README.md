# Kubernetes base

Environment-independent manifests for the platform, assembled by
`kustomization.yaml`. Overlays patch this base; they do not redefine it.

## Workloads

| Manifest | Kind(s) | Notes |
| --- | --- | --- |
| `namespace.yaml` | Namespace | `ai-rag-platform` |
| `configmap.yaml` | ConfigMap `rag-platform-config` | Non-secret service config: internal URLs, timeouts, embedding provider, inference backend, CORS. |
| `secret.yaml` | Secret `rag-platform-secrets` | **Local-dev values only**, matching the Compose stack. Replace with a managed Secret in real environments. |
| `postgres.yaml` | PVC + Deployment + Service | pgvector; 2Gi `ReadWriteOnce` PVC; `Recreate` strategy. |
| `redis.yaml` | Deployment + Service | Cache only — persistence disabled, `allkeys-lru`, ephemeral. |
| `inference.yaml` | Deployment + Service | Deterministic CPU backend by default; the GPU overlay swaps the backend. |
| `retrieval.yaml` | Deployment + Service | `DATABASE_URL` is assembled in-pod from Secret keys so the password is never in a ConfigMap. |
| `agent.yaml` | Deployment + Service | Orchestrates retrieval + inference. |
| `api-gateway.yaml` | Deployment + Service | Public entrypoint; 2 replicas. |
| `web.yaml` | Deployment + Service | Static SPA on nginx; reaches the gateway through the Ingress. |

Service names match the Compose service names, so the internal URLs
(`http://agent:8001`, `http://retrieval:8002`, …) resolve unchanged.

## Probes and resources

Every workload sets `startupProbe`, `readinessProbe`, and `livenessProbe`, plus
CPU/memory `requests` and `limits`:

- The Python services probe `/health` for start-up and liveness. `retrieval` and
  `inference` additionally gate readiness on `/ready`, which reports storage and
  model readiness rather than just process health.
- `postgres` and `redis` probe with `pg_isready` / `redis-cli ping`.
- Start-up probes carry generous `failureThreshold`s so a slow first boot
  (image pull, Postgres initdb) does not trip the liveness probe.

Request values are set low enough to fit a laptop kind cluster; limits are
per-service ceilings, not measured maxima. Tune against the Milestone 6 load
figures for a real cluster.

## Apply

    kubectl apply -k infra/kubernetes/base
    # or an overlay:
    kubectl apply -k infra/kubernetes/overlays/local

Images are referenced as `ai-rag-platform/<service>:latest` with
`imagePullPolicy: IfNotPresent`; build them and load them into the cluster
(`kind load docker-image …`) before applying.
