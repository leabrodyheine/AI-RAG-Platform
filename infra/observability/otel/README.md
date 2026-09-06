# OpenTelemetry Collector

`collector.yaml` is the config mounted into the `otel-collector` service by
`infra/compose/compose.yaml`. It receives OTLP spans from the application
services on ports 4317 (gRPC) and 4318 (HTTP), batches them, and writes them to
the collector log (`debug` exporter) so a request can be followed with
`docker compose logs -f otel-collector`.

Metrics do not flow through the collector: each service exposes Prometheus text
on `/metrics` and Prometheus scrapes those endpoints directly.
