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

`INFERENCE_BACKEND` selects the adapter at startup. All three implement the
same `/generate` contract, so switching is configuration only.

- `deterministic` composes a grounded answer from the `[n]` evidence lines in
  the prompt. It downloads no weights, never uses a GPU, and returns the same
  answer for the same prompt, so the full browser-to-answer path runs in unit
  tests and on CPU-only machines. When the prompt carries no evidence it says
  so rather than inventing an answer.
- `vllm` posts the prompt to an OpenAI-compatible vLLM server at
  `POST /v1/completions` and returns real token counts.
- `triton` posts the prompt to a Triton TensorRT-LLM server at
  `POST /v2/models/{model}/generate`; that endpoint reports no token counts, so
  they are approximated by whitespace splitting.

See [`runtimes/`](../../runtimes/) for starting each GPU server, the pinned
images and configs, and the hardware prerequisites.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `INFERENCE_BACKEND` | `deterministic` | Adapter to run: `deterministic`, `vllm`, or `triton`. |
| `INFERENCE_MODEL` | `deterministic-grounded-v1` | Served model name (`vllm`) or model-repository name such as `ensemble` (`triton`); also reported in responses and `/ready`. |
| `INFERENCE_BACKEND_TIMEOUT_SECONDS` | `30` | Per-request budget for a backend call. |
| `VLLM_BASE_URL` / `TRITON_BASE_URL` | — | Model-server URL; required for that backend. |
| `INFERENCE_STOP_SEQUENCES` | _(none)_ | Comma-separated stop strings applied to every generation. |

Misconfiguration fails at startup: an unknown backend, an empty model name, a
non-positive timeout, or a missing/relative base URL for the selected remote
backend each raise before the service accepts traffic.

## Failure translation

Backend timeouts return `504` and any other backend failure returns `503`. Both
carry a stable `detail` message and the correlation header and never include
internal error text. The agent maps these to the same `503`/`504` it already
returns for retrieval failures, so the public chat contract is unchanged.

## Health

- `GET /health` is process liveness only.
- `GET /ready` reports model readiness: it asks the backend whether it can serve
  a request now and returns `503` with a `not_ready` body while a remote model
  server is still loading weights. The response names the active `backend` and
  `model`. `deterministic` is always ready; `vllm` mirrors `GET /health` and
  `triton` mirrors `GET /v2/models/{model}/ready`.

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

To run against a GPU backend, start a server per [`runtimes/`](../../runtimes/),
then set `INFERENCE_BACKEND`, the matching base URL, and `INFERENCE_MODEL`.
`scripts/smoke_vllm.py` and `scripts/smoke_triton.py` check one real generation
end to end.

## Current boundary

The internal generation contract, the deterministic backend, and the OpenAI
vLLM and Triton TensorRT-LLM backends all serve the same `/generate` route with
stable failure translation and model-aware readiness. Backend choice is
configuration only. Runtime configs are pinned and stop sequences are explicit;
per-request generation parameters still come from the agent's fixed defaults.
Comparing the backends under load is the performance milestone's work.
