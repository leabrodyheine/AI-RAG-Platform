# Project scripts

Add repeatable developer and CI tasks here when they are too involved for the
Makefile. Scripts should be non-interactive and safe to rerun.

## GPU backend smoke tests

`smoke_vllm.py` and `smoke_triton.py` drive one real generation through the same
backend adapter the inference service uses, then print `PASS`/`FAIL` and exit
`0`/`1`. They need a reachable GPU model server and are deliberately excluded
from the automated suite. `_smoke.py` is their shared runner.

```bash
python scripts/smoke_vllm.py --base-url http://localhost:8000 \
  --model meta-llama/Llama-3.1-8B-Instruct
python scripts/smoke_triton.py --base-url http://localhost:8000 --model ensemble
```

See [`runtimes/vllm/README.md`](../runtimes/vllm/README.md) and
[`runtimes/triton/README.md`](../runtimes/triton/README.md) for starting the
servers.

## Kubernetes checks

`validate_k8s_manifests.py` renders `infra/kubernetes/base` and every overlay
with `kubectl kustomize` and checks the invariants the platform depends on:
namespace, probes and resource requests on every container, that each
Deployment's replica count has exactly one owner (a static `replicas` or an
HPA, never both), that Services and the Ingress reference objects that exist,
and that every HPA targets a real Deployment. It needs no cluster. If
`kubeconform` is on PATH it also runs a JSON-schema pass. `make k8s-validate`
wraps it; the pure checks are unit-tested in `tests/`.

```bash
python scripts/validate_k8s_manifests.py
```

`smoke_k8s_deployment.py` runs against a live cluster after `kubectl apply`: it
checks every Deployment in the namespace reports `Available`, and with `--host`
also fetches the SPA at `/` and the gateway health endpoint at `/api/health`
through the Ingress. Not part of the automated suite (no cluster in CI).

```bash
python scripts/smoke_k8s_deployment.py --host rag-platform.local
```
