# vLLM runtime

Runs the reference model behind an OpenAI-compatible API that the inference
service's `vllm` backend calls at `POST /v1/completions`.

## Prerequisites

See [`../README.md`](../README.md) for the shared GPU, driver, memory, and
model-license requirements. In short: one NVIDIA GPU with at least 24 GB of
memory, a recent driver with the NVIDIA Container Toolkit, roughly 20 GB of
disk for weights, and an accepted Llama 3.1 license with a
`HUGGING_FACE_HUB_TOKEN`.

## Pinned versions

| Component | Pin |
| --- | --- |
| Server image | `vllm/vllm-openai:v0.6.3.post1` |
| Model | `meta-llama/Llama-3.1-8B-Instruct` |
| Engine config | [`config/llama-3.1-8b-instruct.yaml`](config/llama-3.1-8b-instruct.yaml) |

## Start the server

From the repository root:

```bash
docker run --rm --gpus all \
  -p 8000:8000 \
  -e HUGGING_FACE_HUB_TOKEN="$HUGGING_FACE_HUB_TOKEN" \
  -v "$HOME/.cache/huggingface:/root/.cache/huggingface" \
  -v "$PWD/runtimes/vllm/config:/config:ro" \
  vllm/vllm-openai:v0.6.3.post1 \
  --config /config/llama-3.1-8b-instruct.yaml
```

The first start downloads the weights. The server is ready when
`GET /health` returns `200`; until then the inference service's `/ready`
reports `not_ready`.

## Verify

```bash
curl -sf http://localhost:8000/health && echo ok
curl -s http://localhost:8000/v1/models | jq '.data[].id'
```

The printed model id must match `INFERENCE_MODEL`.

## Point the inference service at it

```bash
INFERENCE_BACKEND=vllm
VLLM_BASE_URL=http://localhost:8000        # http://host.docker.internal:8000 from Compose
INFERENCE_MODEL=meta-llama/Llama-3.1-8B-Instruct
INFERENCE_BACKEND_TIMEOUT_SECONDS=60
INFERENCE_STOP_SEQUENCES=<|eot_id|>
```

Switching backends is configuration only; no application code changes.

## Smoke test

```bash
python scripts/smoke_vllm.py --base-url http://localhost:8000 \
  --model meta-llama/Llama-3.1-8B-Instruct
```
