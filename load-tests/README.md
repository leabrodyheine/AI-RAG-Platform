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

Against the local fallback stack (no Docker, in-memory retrieval, deterministic
backend) or the Compose stack:

```bash
locust -f load-tests/locustfile.py --host http://localhost:8000 \
  --headless --users 16 --spawn-rate 4 --run-time 60s
```

`evaluation.performance.run` wraps this: it reads a scenario file, runs Locust
headless, samples `/metrics` and host resources, and writes a summary. See
`docs/performance-report.md` for method and results.
