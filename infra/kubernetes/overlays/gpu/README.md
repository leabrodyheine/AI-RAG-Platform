# GPU overlay

Runs real model inference on a GPU. The base stack serves the deterministic
CPU backend; this overlay adds an in-cluster [vLLM](../../../../runtimes/vllm)
server and repoints the inference service at it.

    kubectl apply -k infra/kubernetes/overlays/gpu

## What it changes

| File | Effect |
| --- | --- |
| `vllm.yaml` | New `vllm` Deployment + Service. GPU-scheduled: `runtimeClassName: nvidia`, `nodeSelector: gpu=true`, a toleration for `nvidia.com/gpu=present:NoSchedule`, and `nvidia.com/gpu: 1` in both requests and limits. Serves `meta-llama/Llama-3.1-8B-Instruct` on `POST /v1/completions`. |
| `vllm-config.yaml` | `vllm-engine-config` ConfigMap holding the pinned engine YAML, mounted at `/config`. Mirrors `runtimes/vllm/config/llama-3.1-8b-instruct.yaml`. |
| `inference-patch.yaml` | Replaces the inference container env: `INFERENCE_BACKEND=vllm`, `VLLM_BASE_URL=http://vllm:8000`, `INFERENCE_MODEL=meta-llama/Llama-3.1-8B-Instruct`, plus a 60 s backend timeout and the Llama stop sequence. |

The inference **service** stays on CPU with its base probes and limits — it is
an HTTP client of `vllm`, not a GPU workload. Only the `vllm` pod requests a GPU.

## Cluster prerequisites

The overlay assumes the admin has already:

- installed the **NVIDIA device plugin** so nodes advertise `nvidia.com/gpu`;
- registered a **`nvidia` RuntimeClass** bound to the NVIDIA container runtime;
- labelled GPU nodes `gpu=true` and tainted them
  `nvidia.com/gpu=present:NoSchedule`.

If the cluster uses different labels/taints/runtime-class names, edit the
`nodeSelector`, `tolerations`, and `runtimeClassName` in `vllm.yaml`.

## Secret (not committed)

vLLM needs an accepted Llama 3.1 license token. Create it out of band:

    kubectl -n ai-rag-platform create secret generic vllm-secrets \
      --from-literal=hugging-face-hub-token=hf_xxx

## First start is slow

The `vllm` pod downloads ~20 GB of weights and warms the engine on a cold node.
Its `startupProbe` allows 30 minutes before the pod is declared failed; until
`GET /health` on the vLLM pod returns `200`, the inference service's `/ready`
reports `not_ready` and the gateway keeps the service out of rotation. The
`hf-cache` volume is an `emptyDir`, so weights re-download if the pod changes
nodes — swap in a PVC to persist them.

## Triton / TensorRT-LLM instead of vLLM

The same shape works for Triton; it is not wired up here because it needs a
GPU-specific engine built ahead of time (see
[`runtimes/triton`](../../../../runtimes/triton)). To use it: point `vllm.yaml`
at `nvcr.io/nvidia/tritonserver:24.08-trtllm-python-py3` with the built engine
and `model_repository/` mounted, expose port 8000, and set the inference env to
`INFERENCE_BACKEND=triton`, `TRITON_BASE_URL=http://<svc>:8000`,
`INFERENCE_MODEL=ensemble`.
