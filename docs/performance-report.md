# Performance report

Load evaluation of the RAG chat path: the benchmark setup, the bottleneck the
telemetry pointed at, the optimization made in response, and the measured
before/after result with its limitations.

## Scope

What this report covers:

- End-to-end latency, throughput, and error rate for `POST /chat` under constant
  moderate concurrency.
- Where request time is spent across the four service hops (gateway → agent →
  retrieval → inference), read from the Prometheus metrics each service exports.
- One optimization identified from that evidence, applied, and re-measured on the
  same scenario.

What it does **not** cover, and why:

- **Cached vs. uncached retrieval** and **basic vs. agentic RAG** need Redis and
  Postgres running. **vLLM vs. Triton/TensorRT-LLM** needs a GPU host. None of
  those are available in the environment these numbers were taken on, so the
  method for each is written up in
  [`evaluation/performance/README.md`](../evaluation/performance/README.md)
  rather than reported with numbers here. No performance figure in this document
  is estimated or projected — every number is from a run on this machine.

## Benchmark setup

| Property | Value |
| --- | --- |
| Tool | Locust 2.32.5, driven in-process by `evaluation.performance.run` |
| Scenario | `steady-state` — 16 concurrent users, 120 s, first 15 s dropped as warm-up |
| Stack | `scripts/run_local_stack.py`: web/gateway/agent/retrieval/inference on localhost 8000–8003, no Docker |
| Retrieval | In-memory keyword search over a bundled 4-document corpus (`DATABASE_URL`/`REDIS_URL` unset → offline fallback) |
| Inference | `INFERENCE_BACKEND=deterministic`, model `deterministic-grounded-v1` |
| Tracing | `OTEL_SDK_DISABLED=true` for the measured runs |
| Host | Single machine, CPU only; no GPU present |
| Dataset | `load-tests/dataset/questions.json` (tracked; mix of direct, retrieval, rewrite, and insufficient-evidence questions) |

The deterministic inference backend and the fixed corpus make each run
reproducible: the same question set produces the same answers and the same
retrieval path every time, so run-to-run variation is host scheduling noise
rather than model variance.

Pass/fail thresholds for the scenario (`load-tests/scenarios/steady-state.json`):
error rate ≤ 1%, p95 ≤ 2500 ms, throughput ≥ 5 rps. Every run below passed all
three.

## Bottleneck

The per-run telemetry
([`load-tests/results/steady-state-latest.md`](../load-tests/results/steady-state-latest.md)
for the most recent run) shows the request cost is not in retrieval or
generation. It is fixed framework overhead on each network hop:

| Hop | Server mean | Core work in that hop |
| --- | --- | --- |
| `/chat` (gateway) | 11.2 ms | none — forwards the agent's answer unchanged |
| `/answer` (agent) | 7.6 ms | ~2 ms of downstream calls; the rest is orchestration |
| `/search` (retrieval) | 1.09 ms | 0.10 ms keyword query |
| `/generate` (inference) | 0.87 ms | 0.03 ms deterministic generation |

The retrieval query is 9% of its hop; the generation is 3% of its hop. The
gateway hop is the single largest slice of end-to-end latency — about 32% — and
it transforms nothing. It was parsing the agent's JSON response, running
`ChatResponse.model_validate` on it, and then — because the route declared
`response_model=ChatResponse` — handing that model back to FastAPI, which
validated and serialized the same payload a second time. A
validate → re-validate → re-encode cycle over the largest payloads in the system
(answer text, every citation excerpt, and the full workflow trace) for a hop that
adds no fields.

That redundant pass is the optimization target. It is real work, it scales with
response size and request rate, and removing it changes no output bytes.

## Optimization

[`services/api-gateway/src/api_gateway/routes/chat.py`](../services/api-gateway/src/api_gateway/routes/chat.py):
keep one validation at the contract boundary — it is the public API guarantee —
then return the agent's already-camelCase, already-contract-shaped bytes with
`JSONResponse` instead of giving FastAPI a model to reprocess under
`response_model`. Error paths are unchanged. Response bytes are unchanged. The
full test suite (457 tests) stays green.

## Before / after

Two runs each, alternating baseline and optimized, on the same host. Host CPU is
reported alongside because it drifted between runs and the latency tracked it.

| Run | Host CPU mean / max | `/chat` server mean | `/answer` server mean | overall p50 | overall p95 | RPS | errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline #1 | 36.3% / 49.3% | 11.20 ms | 7.56 ms | 11.39 ms | 24.27 ms | 12.54 | 0 |
| baseline #2 | 46.0% / 69.3% | 12.94 ms | 8.67 ms | 11.93 ms | 35.42 ms | 12.67 | 0 |
| optimized #1 | 39.7% / 64.1% | 12.20 ms | 8.15 ms | 11.93 ms | 29.68 ms | 12.70 | 0 |
| optimized #2 | 37.0% / 54.0% | 11.38 ms | 7.72 ms | 11.24 ms | 27.35 ms | 12.52 | 0 |

At the end-to-end level the change is inside the noise band. The
comparable-load pair — baseline #1 at 36% CPU vs. optimized #2 at 37% CPU —
differs by 0.18 ms on p50, against a run-to-run spread of roughly ±2 ms on this
single machine. p95 and RPS move the same way: within noise.

To measure the change without network and scheduler noise, an isolated
microbenchmark of just the gateway response path — `model_validate` +
`jsonable_encoder(model)` + `json.dumps` (before) vs. `model_validate` +
`json.dumps(raw dict)` (after) — on a realistic 8.2 KB payload (3 citations with
production-scale excerpts, 8 trace steps), 20 000 iterations:

```
before: 100.2 us/req
after :  32.4 us/req   (-68%)
```

So the redundant pass was real and its removal is a clear local win
(~68 µs/request saved, growing with payload size and request rate), but at
~0.07 ms it sits well under the end-to-end noise floor of this stack, which is
why the scenario totals do not visibly move.

The fuller write-up, including the per-hop reasoning, is in
[`evaluation/performance/results/steady-state-optimization.md`](../evaluation/performance/results/steady-state-optimization.md).

## Reading of the result

On this CPU-only, single-host stack the chat path is **fixed-overhead-bound, not
hotspot-bound**. End-to-end latency is spread across four ASGI/httpx hops with no
single dominant cost, so no one application-level change moves p50 above host
scheduling noise. The levers that would actually move the number are structural —
hop count and payload size — not any single handler. The same redundant
validate/serialize pattern is still present on the agent's `/answer` route and is
noted as a follow-up.

## Limitations

- **CPU only, single host.** No GPU, no container isolation, no separate machines.
  Network hops are loopback. Absolute latencies are not representative of a
  deployed cluster; the *shape* (overhead spread across hops) is the
  transferable finding.
- **Deterministic inference backend.** Generation is ~0.03 ms. A real model
  would dominate end-to-end latency and shift the bottleneck entirely to the
  inference hop. This benchmark measures the platform overhead *around*
  inference, not inference itself.
- **In-memory retrieval.** No pgvector, no embedding model, no cache. Retrieval
  latency here is a keyword scan over 4 documents.
- **Run-to-run noise ≈ ±2 ms** on end-to-end percentiles, driven by host CPU
  contention. Differences smaller than that between runs are not meaningful; the
  isolated microbenchmark exists because of this.
- **Small corpus and dataset.** Payload sizes in the load runs are smaller than
  the 8.2 KB used in the microbenchmark, which is itself modest.

## Reproducibility

From a clean checkout with the virtualenv created and `load-tests/requirements.txt`
installed:

```bash
# Start the four-service CPU stack, run the scenario, tear down, write a summary:
make load-run SCENARIO=steady-state

# Against an already-running stack:
python -m evaluation.performance.run steady-state --host http://127.0.0.1:8000
```

The runner writes `load-tests/results/<scenario>-<timestamp>.{json,md}`
(git-ignored). Fixed configuration for the runs in this report, set by
`scripts/run_local_stack.py`:

| Setting | Value |
| --- | --- |
| `OTEL_SDK_DISABLED` | `true` |
| `DATABASE_URL`, `REDIS_URL` | unset (offline fallback) |
| `INFERENCE_BACKEND` | `deterministic` |
| Service ports | gateway 8000, agent 8001, retrieval 8002, inference 8003 |
| Scenario file | `load-tests/scenarios/steady-state.json` (16 users, 120 s, 15 s warm-up) |
| Python | 3.11.0 |

Because the backend is deterministic and the corpus is fixed, a rerun reproduces
the same answers and retrieval decisions. Latency percentiles will differ within
the noted noise band depending on host load.

## Comparisons requiring more infrastructure

These are part of Milestone 6's goal but need infrastructure not present here.
The method for each — scenarios, configuration flags, and what to compare — is in
[`evaluation/performance/README.md`](../evaluation/performance/README.md):

- **Cached vs. uncached retrieval** — `cached` / `uncached` scenarios with Redis
  and Postgres up.
- **Basic vs. agentic RAG** — `AGENT_WORKFLOW_MIN_RELEVANCE` toggled to disable
  or enable the rewrite/retry loop.
- **vLLM vs. Triton/TensorRT-LLM** — `INFERENCE_BACKEND` on a GPU host with the
  pinned runtime configs.
