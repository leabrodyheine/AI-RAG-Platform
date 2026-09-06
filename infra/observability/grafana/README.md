# Grafana

`provisioning/` wires Grafana up on startup with no manual clicks:

- `provisioning/datasources/prometheus.yaml` — the Prometheus datasource
  (uid `prometheus`).
- `provisioning/dashboards/dashboards.yaml` — a file provider that loads every
  dashboard in `dashboards/`.
- `dashboards/rag-platform-overview.json` — health, request rate, error rate,
  inbound/outbound latency, retrieval cache and query latency, and inference
  generation, throughput, and time-to-first-token.

`infra/compose/compose.yaml` mounts both directories and exposes Grafana on
http://localhost:3001 (anonymous viewer access is on; admin/admin to edit).
