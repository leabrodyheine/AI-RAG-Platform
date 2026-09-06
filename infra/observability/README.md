# Observability

Keep telemetry collector, scrape, dashboard, and datasource configuration under
the tool-specific directories here. Application instrumentation lives in
`libs/observability/` and is applied by each service.

- `otel/collector.yaml` — receives OTLP spans, logs them.
- `prometheus/prometheus.yml` — scrapes `/metrics` on every service.
- `grafana/` — provisioned Prometheus datasource and the overview dashboard.

The Compose stack (`infra/compose/compose.yaml`) runs all three. See
`docs/operations/observability.md` for usage.
