# rag-platform-observability

Shared logging, tracing, and metrics wiring so every FastAPI service exposes the
same signals the same way. Installed editable alongside the services
(`make install-python`).

```python
from rag_observability import instrument_app

app = FastAPI(...)
instrument_app(app, "retrieval")
```

`instrument_app` configures JSON logging and OpenTelemetry for the service,
instruments inbound requests and outbound `httpx` calls, adds a middleware that
resolves/binds/echoes `X-Request-ID` and records `http_server_*` metrics, and
mounts `GET /metrics`.

Also exported:

- `client_event_hooks(service, target)` — pass to an `httpx.AsyncClient` for
  outbound `http_client_*` metrics.
- `record_cache_event`, `observe_retrieval_query`, `record_generation` — the
  retrieval-cache and inference domain metrics.
- `get_tracer(name)` — for domain spans (`agent.plan`, `retrieval.search`, ...).
- `current_request_id`, `current_trace_ids` — for correlation in handlers.

Configuration is by environment: `LOG_LEVEL`, `OTEL_EXPORTER_OTLP_ENDPOINT`
(unset = record spans in-process only), `OTEL_SDK_DISABLED=true` (tracing off).

See `docs/operations/observability.md` for how the signals are used.
