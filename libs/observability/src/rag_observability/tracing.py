"""OpenTelemetry tracer setup shared by every service.

``configure_tracing`` installs a :class:`TracerProvider` whose resource names the
service. When ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set (the Compose stack points it
at the collector) spans are batched to that OTLP/HTTP endpoint; otherwise the
provider still records spans in-process so tests can assert on them, it just does
not export. Setting ``OTEL_SDK_DISABLED=true`` turns tracing off entirely.
"""

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import format_span_id, format_trace_id

_INSTRUMENTATION_SCOPE = "rag-platform"

_configured_service: str | None = None


def configure_tracing(
    service_name: str,
    *,
    resource_attributes: dict[str, str] | None = None,
) -> None:
    """Set the global tracer provider for ``service_name`` once per process."""
    global _configured_service
    if _configured_service is not None:
        return
    if os.getenv("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        _configured_service = service_name
        return

    attributes = {SERVICE_NAME: service_name, **(resource_attributes or {})}
    provider = TracerProvider(resource=Resource.create(attributes))

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    trace.set_tracer_provider(provider)
    _configured_service = service_name


def get_tracer(name: str = _INSTRUMENTATION_SCOPE) -> trace.Tracer:
    """Return a tracer, safe to call before :func:`configure_tracing`."""
    return trace.get_tracer(name)


def current_trace_ids() -> tuple[str | None, str | None]:
    """Return ``(trace_id, span_id)`` as zero-padded hex, or ``(None, None)``."""
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None, None
    return format_trace_id(context.trace_id), format_span_id(context.span_id)
