# Performance results (tracked)

Curated before/after summaries for optimizations measured with the load
harness. These are hand-written and reviewed; the raw per-run JSON and Markdown
that the harness emits live in `load-tests/results/` and are git-ignored.

- `steady-state-optimization.md` — the gateway response pass-through change,
  measured on the `steady-state` scenario.

Reproduce a run with `make load-run SCENARIO=steady-state` (see
`load-tests/README.md`). The narrative report is `docs/performance-report.md`.
