# Steady-state optimization: gateway response pass-through

Scenario: `steady-state` (16 concurrent users, 120 s, 15 s warm-up dropped).
Stack: `scripts/run_local_stack.py` — four services on one host, in-memory
retrieval, deterministic inference, no Docker/Redis/GPU. CPU-only.

## Bottleneck

The per-run telemetry (`load-tests/results/steady-state-latest.md`) shows the
work is not in retrieval or generation — it is fixed framework overhead on each
network hop:

| Hop | Server mean | Core work in that hop |
| --- | --- | --- |
| `/chat` (gateway) | 11.2 ms | none — forwards the agent's answer unchanged |
| `/answer` (agent) | 7.6 ms | ~2 ms downstream calls, rest is orchestration |
| `/search` (retrieval) | 1.09 ms | 0.10 ms keyword query |
| `/generate` (inference) | 0.87 ms | 0.03 ms deterministic generation |

The gateway hop is ~32% of end-to-end latency while transforming nothing. It
parsed the agent's JSON, ran `ChatResponse.model_validate` on it, then — because
the route returned that model under `response_model=ChatResponse` — FastAPI
validated and serialized the same payload a second time. A validate → re-validate
→ re-encode cycle over the largest payloads in the system (answer text + every
citation excerpt + the full trace), for a hop that adds no fields.

## Change

`services/api-gateway/src/api_gateway/routes/chat.py`: validate the agent payload
once at the contract boundary (kept — it is the public API guarantee), then
return the agent's already-camelCase bytes via `JSONResponse` instead of handing
FastAPI a model to reprocess. Response bytes are unchanged; 457 tests green.

## Before / after

Two runs each, alternating, same host. Host CPU is reported because it moved
between runs and the latency tracked it.

| Run | Host CPU mean / max | `/chat` server mean | `/answer` server mean | overall p50 | overall p95 | RPS | errors |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline #1 | 36.3% / 49.3% | 11.20 ms | 7.56 ms | 11.39 ms | 24.27 ms | 12.54 | 0 |
| baseline #2 | 46.0% / 69.3% | 12.94 ms | 8.67 ms | 11.93 ms | 35.42 ms | 12.67 | 0 |
| optimized #1 | 39.7% / 64.1% | 12.20 ms | 8.15 ms | 11.93 ms | 29.68 ms | 12.70 | 0 |
| optimized #2 | 37.0% / 54.0% | 11.38 ms | 7.72 ms | 11.24 ms | 27.35 ms | 12.52 | 0 |

`/chat` server mean tracks host CPU load, not the code change. The
comparable-load pair (baseline #1 at 36% CPU vs optimized #2 at 37%) differs by
0.18 ms — inside the run-to-run noise band of roughly ±2 ms on this single
machine.

## Isolated measurement

Removing the network and scheduler noise, a microbenchmark of just the gateway
response path (`ChatResponse.model_validate` + `jsonable_encoder(model)` +
`json.dumps` vs `model_validate` + `json.dumps(raw dict)`) on a realistic 8.2 KB
payload — 3 citations with production-scale excerpts, 8 trace steps, 20 000
iterations:

```
before: 100.2 us/req
after :  32.4 us/req   (-68%)
```

Real work removed, and it is O(response size) per request, so it grows with
corpus/excerpt size and request rate. At ~0.07 ms per request it is well below
the end-to-end noise floor on one CPU host, which is why the scenario totals do
not move.

## Reading of the result

On this CPU-only, single-host stack the chat path is fixed-overhead-bound, not
hotspot-bound: latency is spread across four ASGI/httpx hops with no single
dominant cost, so no one application-level change moves end-to-end p50 above
host-scheduling noise. The redundant validate/serialize was a genuine
inefficiency worth removing (and the same pattern on the agent `/answer` route
was given the same treatment), but the architectural levers that would actually
move this number are hop count and payload size, not any one handler.
