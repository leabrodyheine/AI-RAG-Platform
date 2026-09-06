from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from rag_observability.tracing import (
    configure_tracing,
    current_trace_ids,
    get_tracer,
)


def test_configure_tracing_installs_a_provider_once() -> None:
    configure_tracing("agent")
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)

    configure_tracing("agent-again")
    assert trace.get_tracer_provider() is provider


def test_current_trace_ids_are_none_outside_a_span() -> None:
    assert current_trace_ids() == (None, None)


def test_current_trace_ids_are_hex_inside_a_span() -> None:
    configure_tracing("agent")
    with get_tracer("test").start_as_current_span("unit"):
        trace_id, span_id = current_trace_ids()

    assert trace_id is not None and len(trace_id) == 32
    assert span_id is not None and len(span_id) == 16
    int(trace_id, 16)
    int(span_id, 16)
