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

## Running

The stack must already be up. For the offline fallback stack:

    python scripts/run_local_stack.py &            # gateway on :8000
    python -m evaluation.performance.run smoke --host http://localhost:8000
    python -m evaluation.performance.run steady-state --host http://localhost:8000 --check-pass-fail

Reports default to `load-tests/results/<scenario>-latest.{json,md}`, which is
git-ignored; only hand-picked summaries are committed.

## Not covered by the automated run

- **CPU / memory / GPU utilisation** — sampled alongside the run; GPU figures are
  only present on a GPU host.
- **cached vs uncached** — the `cached` scenario needs Postgres and Redis
  (`docker compose up postgres redis` from `infra/compose/`); every other
  scenario runs on the offline fallback stack.
- **basic vs agentic RAG** — set `AGENT_WORKFLOW_MIN_RELEVANCE=0.0` (basic; the
  rewrite step never fires) against `0.3` (agentic, the default) on the stack.
- **vLLM vs Triton/TensorRT-LLM** — needs a GPU host; select with
  `INFERENCE_BACKEND`.
