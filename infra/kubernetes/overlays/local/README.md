# Local overlay

Runs the base stack on a single-node [kind](https://kind.sigs.k8s.io) cluster.
It keeps the base as-is except for dropping `api-gateway` and `web` to one
replica each.

## Bring it up

```bash
# 1. Cluster with the ingress host-ports mapped through.
kind create cluster --name ai-rag \
  --config infra/kubernetes/overlays/local/kind-cluster.yaml

# 2. ingress-nginx (kind build) and wait for it.
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx wait --for=condition=Ready pod \
  --selector=app.kubernetes.io/component=controller --timeout=180s

# 3. Build the service images and load them into the node. The web image needs
#    the ingress path baked in at build time.
for svc in api-gateway agent retrieval inference; do
  docker build -t ai-rag-platform/$svc:latest services/$svc
done
docker build -t ai-rag-platform/web:latest \
  --build-arg VITE_API_BASE_URL=http://rag-platform.local/api apps/web
kind load docker-image --name ai-rag \
  ai-rag-platform/{api-gateway,agent,retrieval,inference,web}:latest

# 4. Apply.
kubectl apply -k infra/kubernetes/overlays/local
kubectl -n ai-rag-platform wait --for=condition=Available deploy --all --timeout=300s
```

Add `127.0.0.1 rag-platform.local` to `/etc/hosts`, then open
<http://rag-platform.local>. The API is at `http://rag-platform.local/api`.

## Data-loss expectations

**This is a throwaway environment. Do not put anything in it you need to keep.**

- **PostgreSQL** uses a `PersistentVolumeClaim` (`postgres-data`, 2Gi), so data
  survives a pod restart or a `kubectl apply`. It does **not** survive
  `kind delete cluster` — kind's storage is a directory inside the node
  container, deleted with it. It also does not survive deleting the PVC, which
  `kubectl delete -k` does.
- The Deployment uses the `Recreate` strategy with one replica: during any
  rollout Postgres is briefly down (no HA here).
- **Redis** has persistence disabled and is cache-only; every restart starts
  cold. The application treats a cache miss as normal, so this only costs
  latency on the first request after a restart.
- **Ingested documents and embeddings** live in Postgres, so they follow the
  Postgres rules above. Re-run ingestion after recreating the cluster.
- The Hugging Face weight cache in the GPU overlay is an `emptyDir` and is lost
  with the pod.

For data that must persist across cluster recreation, point the PVC at a real
StorageClass with a retained volume, or run Postgres outside the cluster.
