# Prometheus

`prometheus.yml` is mounted into the `prometheus` service by
`infra/compose/compose.yaml`. It scrapes `/metrics` on the api-gateway, agent,
retrieval, and inference services every 10s, plus the collector's own telemetry
endpoint. Local retention is short (`--storage.tsdb.retention.time=6h`).

Open the UI at http://localhost:9090. Alert rules would live alongside this file
and be referenced from `rule_files:`.
