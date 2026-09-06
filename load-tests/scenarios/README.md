# Load-test scenarios

One JSON file per named profile, schema `load-scenario/v1`, validated by
`evaluation.performance.scenarios`. The file stem is the scenario name used on
the command line.

| Scenario | Load | Purpose |
| --- | --- | --- |
| `smoke` | 4 users, 20s | Gate: the chat path answers before a long run starts. |
| `steady-state` | 16 users, 2m | Baseline; the before/after optimization is compared here. |
| `ramp` | 8 → 32 users in 45s steps | Find the concurrency where p95 / error rate climbs. |
| `burst` | 4 → 48 → 4 users | Absorb a spike and recover afterwards. |
| `uncached` | 16 users, 2m, no Redis | Retrieval pays full cost every question. |
| `cached` | 16 users, 2m, Redis | Repeated questions served from cache; compared to `uncached`. |

## Fields

- `warmup` — leading span (`"15s"`) excluded from the scored aggregates.
- `stages` — run top to bottom; each holds `users` for `duration` at
  `spawn_rate`. A single stage holds load constant.
- `wait_min` / `wait_max` — per-user think time in seconds (default `0.5` / `2.0`).
- `question_set` — path to the question set (default
  `load-tests/dataset/questions.json`).
- `env` — environment applied to the stack the local runner starts, e.g.
  `cached` points retrieval at Postgres and Redis. Ignored when running against
  an already-configured Compose stack.
- `pass_fail` — `max_error_rate` (0–1), `max_p95_ms`, and optional
  `min_throughput_rps`, checked against the scored window.

`docker compose up postgres redis` (from `infra/compose/`) provides the backing
store the `cached` scenario needs; every other scenario runs on the offline
fallback stack with no Docker.
