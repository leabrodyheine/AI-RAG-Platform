# Observability

Every service is wired the same way by `rag_observability.instrument_app`
(`libs/observability/`): structured JSON logs, OpenTelemetry traces, and
Prometheus metrics. The Compose stack adds an OpenTelemetry Collector,
Prometheus, and Grafana.

| Signal | Where it goes | How to read it |
| --- | --- | --- |
| Logs | stderr of each service, one JSON object per line | `docker compose logs -f <service>` |
| Traces | OTLP/HTTP to `otel-collector:4318`, logged by the collector | `docker compose logs -f otel-collector` |
| Metrics | `GET /metrics` on each service, scraped by Prometheus | Prometheus <http://localhost:9090>, Grafana <http://localhost:3001> |

## Follow one request end to end

Every log line and span carries a `request_id` (the browser's `X-Request-ID`,
or one minted by the gateway) and a `trace_id`. They are the same value across
the gateway, agent, retrieval, and inference services for a single chat request.

1. Make a request with a known id:

   ```bash
   curl -sS -X POST http://localhost:8000/chat \
     -H 'Content-Type: application/json' \
     -H 'X-Request-ID: demo-001' \
     -d '{"question": "What is driving p95 latency?"}'
   ```

2. Filter every service's logs for it:

   ```bash
   docker compose logs --no-log-prefix | grep '"request_id":"demo-001"'
   ```

   The lines are ordered gateway -> agent -> retrieval -> inference and share
   one `trace_id`. Grab that `trace_id` and grep the collector log for the full
   span tree:

   ```bash
   docker compose logs otel-collector | grep <trace_id>
   ```

## Metrics reference

All series carry a `service` label. Histograms expose `_bucket`, `_sum`, and
`_count`.

| Metric | Meaning |
| --- | --- |
| `http_server_requests_total{method,route,status}` | inbound requests; `status` is the class (`2xx`, `4xx`, `5xx`) |
| `http_server_request_duration_seconds` | inbound latency |
| `http_client_requests_total{target,status}` / `http_client_request_duration_seconds{target}` | outbound calls to `agent` / `retrieval` / `inference` |
| `retrieval_cache_events_total{result}` | `hit`, `miss`, or `bypass` |
| `retrieval_query_duration_seconds{path}` | query time by `memory`, `postgres`, or `cache` |
| `inference_generation_duration_seconds{backend,model}` | one generation call |
| `inference_tokens_total{backend,model,kind}` | `prompt` and `completion` token counts |
| `inference_time_to_first_token_seconds` | streaming backends only; empty on the CPU-only deterministic stack |

### Useful PromQL

```promql
# Request rate per service
sum by (service) (rate(http_server_requests_total[5m]))

# 5xx error ratio per service
sum by (service) (rate(http_server_requests_total{status="5xx"}[5m]))
  / sum by (service) (rate(http_server_requests_total[5m]))

# Inbound p95 latency per service
histogram_quantile(0.95,
  sum by (le, service) (rate(http_server_request_duration_seconds_bucket[5m])))

# Cache hit ratio
sum(rate(retrieval_cache_events_total{result="hit"}[5m]))
  / sum(rate(retrieval_cache_events_total[5m]))

# Inference completion throughput (tokens/sec)
sum(rate(inference_tokens_total{kind="completion"}[5m]))

# Generation p95
histogram_quantile(0.95,
  sum by (le) (rate(inference_generation_duration_seconds_bucket[5m])))
```

## Grafana

`RAG Platform Overview` (folder: RAG Platform) is provisioned from
`infra/observability/grafana/dashboards/rag-platform-overview.json` and covers
health, request/error rate, inbound and outbound latency, retrieval cache and
query latency, and inference generation, throughput, and time to first token —
the inputs the performance report needs. Anonymous viewer access is on;
`admin` / `admin` to edit.

## Common signatures

| Symptom | Look at |
| --- | --- |
| Slow chat, fast services | `http_client_request_duration_seconds` on the gateway/agent vs `http_server_request_duration_seconds` on the callee — the gap is network/queueing |
| Slow retrieval | `retrieval_query_duration_seconds{path="postgres"}` high and `retrieval_cache_events_total{result="miss"}` climbing -> cold or churning cache |
| Slow answers | `inference_generation_duration_seconds` p95; check `inference_tokens_total` for oversized prompts |
| 5xx spike in one service | grep that service's logs for the `trace_id` from a failing request; the `exception` field has the traceback |

## Turning tracing off

Unset `OTEL_EXPORTER_OTLP_ENDPOINT` to keep spans in-process only (no exporter),
or set `OTEL_SDK_DISABLED=true` to disable tracing entirely. Metrics and logs
are unaffected. The test suite runs with no endpoint set.
