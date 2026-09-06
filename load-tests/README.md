# Load tests

Reproducible load profiles for the RAG chat path.

## Tool

[Locust](https://locust.io/) `2.32.5`, pinned in `requirements.txt`. It is pure
Python, so it installs into the same virtualenv as the services and its
scenarios reuse the project dataset and contracts directly. Install it with:

```bash
python -m pip install -r load-tests/requirements.txt
```

## Layout

- `locustfile.py` — the driver: one `ChatUser` that POSTs `/chat` with questions
  from `dataset/questions.json`, tags each request by question kind, and gives
  every request a unique `X-Request-ID` so a slow one can be found in traces.
- `dataset/questions.json` — the tracked, offline-reproducible question set.
- `scenarios/` — named profiles (users, spawn rate, run time, pass/fail
  criteria). Reproducible; tracked.
- `results/` — raw Locust output. Ignored by Git; publishable summaries go to
  `docs/performance-report.md`.

## Running

`scripts/run_local_stack.py` boots the four services on localhost with no Docker
(in-memory retrieval, deterministic inference) and can run a scenario end to end:

```bash
make load-smoke                       # start stack, run the smoke scenario, tear down
make load-run SCENARIO=steady-state   # same, for any scenario
python scripts/run_local_stack.py     # just hold the stack up (Ctrl-C to stop)
```

`evaluation.performance.run` is the harness underneath: it reads a scenario
file, drives the load with Locust embedded in the process, samples `/metrics`
and host resources, scores the post-warm-up window, and writes a JSON + Markdown
summary to `results/` (git-ignored). Against an already-running stack:

```bash
python -m evaluation.performance.run steady-state --host http://localhost:8000
```

Or drive Locust directly:

```bash
locust -f load-tests/locustfile.py --host http://localhost:8000 \
  --headless --users 16 --spawn-rate 4 --run-time 60s
```

See `docs/performance-report.md` for method and results.
