"""Shared observability wiring for the platform's FastAPI services.

Every service configures the same three signals the same way:

- **Structured logs** as one JSON object per line, always carrying the service
  name and, when a request is in scope, its request and trace identifiers.
- **Traces** through OpenTelemetry, exported to an OTLP collector when
  ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set and otherwise recorded in-process only.
- **Metrics** in Prometheus text format on ``/metrics``, using one shared
  registry so a service exposes exactly the series defined here.

``instrument_app(app, service_name)`` applies all of it to a FastAPI app:
inbound/outbound HTTP spans, a request/trace-id middleware, an access log, HTTP
server metrics, and the ``/metrics`` endpoint.
"""

from rag_observability.context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    current_request_id,
    new_request_id,
    resolve_request_id,
)
from rag_observability.http_client import client_event_hooks
from rag_observability.instrumentation import instrument_app
from rag_observability.logging import configure_logging
from rag_observability.metrics import REGISTRY, render_latest
from rag_observability.tracing import (
    configure_tracing,
    current_trace_ids,
    get_tracer,
)

__all__ = [
    "REGISTRY",
    "REQUEST_ID_HEADER",
    "bind_request_id",
    "client_event_hooks",
    "configure_logging",
    "configure_tracing",
    "current_request_id",
    "current_trace_ids",
    "get_tracer",
    "instrument_app",
    "new_request_id",
    "render_latest",
    "resolve_request_id",
]
