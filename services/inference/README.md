# Inference service

The inference service turns a fully constructed prompt into an answer. It owns
no retrieval or prompt-building logic: the agent sends the complete prompt and
the generation controls, and this service runs the configured backend and
returns the text with its token accounting.

- `POST /generate` accepts a `prompt` (1–20,000 characters), `maxTokens`
  (1–2048), and `temperature` (0–2), and returns `content`, the `model`
  identity, and `usage` token counts. Successful and error responses carry an
  `X-Request-ID` correlation header, generated when the caller omits one.

The contract is `contracts/openapi/inference-v1.openapi.json`.

## Backends

`INFERENCE_BACKEND` selects the adapter at startup:

- `deterministic` composes a grounded answer from the `[n]` evidence lines in
  the prompt. It downloads no weights, never uses a GPU, and returns the same
  answer for the same prompt, so the full browser-to-answer path runs in unit
  tests and on CPU-only machines. When the prompt carries no evidence it says
  so rather than inventing an answer.

The OpenAI-compatible vLLM and Triton/TensorRT-LLM backends arrive with the GPU
inference milestone and implement the same `/generate` contract.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `INFERENCE_BACKEND` | `deterministic` | Backend adapter to run. |
| `INFERENCE_MODEL` | `deterministic-grounded-v1` | Model identity reported in responses and `/ready`. |
| `INFERENCE_BACKEND_TIMEOUT_SECONDS` | `30` | Per-request budget for a backend call. |

Misconfiguration fails at startup: an unknown backend, an empty model name, or
a non-positive timeout each raise before the service accepts traffic.

## Failure translation

Backend timeouts return `504` and any other backend failure returns `503`. Both
carry a stable `detail` message and the correlation header and never include
internal error text. The agent maps these to the same `503`/`504` it already
returns for retrieval failures, so the public chat contract is unchanged.

## Health

- `GET /health` is process liveness.
- `GET /ready` additionally reports the active model. The GPU backends will
  extend it to distinguish service health from model readiness.

## Local workflow

Start the service from the repository root:

```bash
docker compose -f infra/compose/compose.yaml up --build inference
```

Generate an answer from a prompt that already contains its evidence:

```bash
curl -X POST http://localhost:8003/generate \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: local-generate-1' \
  -d '{
    "prompt": "Question: What raised p95?\n\nEvidence:\n[1] Retrieval benchmark — Cache misses raised vector-search p95 to 391 ms.\n\nAnswer using only the evidence above.",
    "maxTokens": 256,
    "temperature": 0.1
  }'
```

The deterministic backend answers from `[1]` and cites it by number. Run the
same request twice to confirm the output is identical.

## Current boundary

This milestone provides the internal generation contract, validated request and
response schemas, the deterministic backend, and the `/generate` route with
stable failure translation. The agent now retrieves evidence, builds a grounded
prompt, and generates the answer through this service. The GPU backends,
readiness that separates service and model health, and reproducible model and
tokenizer settings are the next vertical slice.
