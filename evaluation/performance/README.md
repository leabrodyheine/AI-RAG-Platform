# Performance evaluation

The load-test scenarios live in `load-tests/scenarios/` (schema `load-scenario/v1`).
This package loads them and runs them.

## Modules

- `scenarios.py` — scenario schema, loader, and validation.
- `run.py` — `python -m evaluation.performance.run <scenario> --host <url>`. Runs
  the scenario's stages in order with Locust embedded in the process, records one
  entry per completed request, and writes a JSON + Markdown report.
- `aggregate.py` — drops the warm-up window, then reduces the rest to latency
  percentiles (p50/p90/p95/p99), throughput, and error rate, overall and split by
  request name, and checks the scenario's `pass_fail` thresholds.
- `report.py` — assembles the scored run into the machine-readable and
  human-readable reports.
- `telemetry.py` — scrapes each service's `/metrics` and samples host CPU/memory
  (and GPU util/memory when `nvidia-smi` is present) for the duration of the run.

## Running

The stack must already be up. For the offline fallback stack:

    python scripts/run_local_stack.py &            # gateway on :8000
    python -m evaluation.performance.run smoke --host http://localhost:8000
    python -m evaluation.performance.run steady-state --host http://localhost:8000 --check-pass-fail

Reports default to `load-tests/results/<scenario>-latest.{json,md}`, which is
git-ignored; only hand-picked summaries are committed. The narrative report is
`docs/performance-report.md`; reviewed before/after summaries live in
`evaluation/performance/results/`.

## Comparisons that need more infrastructure

Milestone 6 calls for three comparisons that cannot run on the CPU-only offline
fallback stack. The measured bottleneck and before/after in
`docs/performance-report.md` were taken on that stack; the comparisons below are
**method only** — scenarios, configuration, procedure, and what to read — with no
numbers, because the environments to run them were not available here. Each uses
the same harness (`python -m evaluation.performance.run <scenario>`) and the same
scored report.

### 1. Cached vs. uncached retrieval

**Question.** How much does the Redis retrieval cache lower retrieval latency and
its tail under steady load, once the corpus is real (pgvector) rather than the
in-memory keyword fallback.

**Infrastructure.** Postgres and Redis:

    cd infra/compose && docker compose up -d postgres redis

Then start the four services with `DATABASE_URL` and `REDIS_URL` pointed at those
published ports, ingest the evaluation corpus so retrieval has documents to
score, and let the embedding provider warm.

**Scenarios.** `uncached` (no `REDIS_URL` in its `env` block — every question
pays full retrieval cost) and `cached` (its `env` block sets both
`DATABASE_URL` and `REDIS_URL`; `warmup` is 25 s so the cache is populated before
the measured window). Both run one 120 s stage at 16 users, spawn rate 4. Run
`uncached` first, then `cached` against the same running stack:

    python -m evaluation.performance.run uncached --host http://localhost:8000
    python -m evaluation.performance.run cached   --host http://localhost:8000

**Read.** Compare the `/search` route percentiles (p50/p95/p99) and RPS between
the two reports, and the `retrieval_query_duration_seconds` server metric split
by `path` (`vector` vs `cache`). Confirm the cache is actually being exercised
with `retrieval_cache_events_total{result=...}` — `hit` should dominate in the
`cached` run and be absent in `uncached`. The `cached` scenario's `pass_fail`
sets `max_p95_ms` to 1500 vs. 2500 for `uncached`; the gap between the two p95s
is the cache's effect. For cold-cache behaviour, run `burst` with and without
`REDIS_URL` and compare the first-stage spike.

### 2. Basic vs. agentic RAG

**Question.** What the bounded rewrite/retry loop costs in latency and throughput,
and how often it fires, versus a single retrieval pass.

**Infrastructure.** None beyond the normal stack — this toggles agent behaviour
only. Use a corpus where some questions retrieve weak evidence (the evaluation
dataset already mixes direct, retrieval, rewrite, and insufficient-evidence
questions) so the loop has something to react to.

**Configuration.** The agent service reads `AGENT_WORKFLOW_MIN_RELEVANCE`
(`services/agent/src/agent_service/config.py`, clamped to `[0.0, 1.0]`, default
`0.3`). It is the similarity floor `assess_evidence` uses to decide whether
evidence is strong enough; when it is not, the workflow spends its one rewrite
and retries.

- **Basic:** `AGENT_WORKFLOW_MIN_RELEVANCE=0.0`. Every retrieved citation counts
  as usable, so a single result is always "strong" and the rewrite branch never
  fires on relevance grounds — one retrieval pass per question.
- **Agentic:** `AGENT_WORKFLOW_MIN_RELEVANCE=0.3` (the default). Weak retrievals
  trigger the bounded rewrite and second search.

**Procedure.** Run `steady-state` twice against the same stack, restarting only
the agent service with the changed env var between runs:

    AGENT_WORKFLOW_MIN_RELEVANCE=0.0 <restart agent>
    python -m evaluation.performance.run steady-state --host http://localhost:8000
    AGENT_WORKFLOW_MIN_RELEVANCE=0.3 <restart agent>
    python -m evaluation.performance.run steady-state --host http://localhost:8000

**Read.** Compare overall p50/p95 and RPS. In the scored report the per-request
split by name shows the `[rewrite]`-tagged `/chat` questions; in the agentic run
those carry the extra retrieval hop, and the fraction of traffic on that tag is
how much of the workload the loop touched. The `/answer` server-duration metric
should rise for the agentic run by roughly one retrieval hop on the affected
questions. Error rate must stay at 0 for both — the loop is a quality mechanism,
not a correctness risk.

### 3. vLLM vs. Triton/TensorRT-LLM

**Question.** Inference latency, time-to-first-token, and token throughput of the
two GPU backends under equivalent generation settings.

**Infrastructure.** A GPU host. Pinned runtime configs and start-up instructions
are in `runtimes/vllm/` and `runtimes/triton/` (shared GPU/driver/model-license
prerequisites in `runtimes/README.md`). Both serve
`meta-llama/Llama-3.1-8B-Instruct`. Start one backend, wait for the inference
service's `/ready` to report `ready` (model-loaded, distinct from process
health), then run; repeat for the other.

**Configuration.** `INFERENCE_BACKEND=vllm` vs `INFERENCE_BACKEND=triton` on the
inference service. Hold everything else equal: same model, same stop sequences
and generation parameters (the agent's fixed per-request defaults; tokenizer is
pinned to each model repo), same scenario, same client concurrency. Do not change
the agent or gateway between runs.

**Procedure.** Run `steady-state` against each backend for the latency/throughput
comparison, and `ramp` and `burst` for scaling and cold-start behaviour:

    # backend A up and model-ready
    python -m evaluation.performance.run steady-state --host http://localhost:8000
    python -m evaluation.performance.run ramp        --host http://localhost:8000
    # swap to backend B, wait for model-ready, repeat

**Read.** From the server metrics in each report: `inference_generation_duration_seconds`
(generation latency), `inference_time_to_first_token_seconds` (TTFT — emitted by
streaming backends), and tokens/sec computed as `inference_tokens_total{kind=output}`
over the run duration. From the telemetry sampler: GPU utilisation and GPU memory,
which are only populated on a GPU host. At the request level compare overall
p50/p95 and RPS. Keep the two runs' prompt sets identical so token counts are
comparable; report the pinned image tags and config files from `runtimes/` next
to the numbers.
