"""Prometheus instrumentation for outbound HTTP calls.

OpenTelemetry's httpx instrumentation already puts every outbound call on a span;
this adds the Prometheus counterpart so client-observed latency and error rates
show up on ``/metrics`` too. Services opt in by passing :func:`client_event_hooks`
to their :class:`httpx.AsyncClient`.
"""

from time import perf_counter
from typing import Any

from rag_observability.metrics import (
    http_client_request_duration_seconds,
    http_client_requests_total,
)

_START_KEY = "rag_client_start"


def client_event_hooks(service_name: str, target: str) -> dict[str, list[Any]]:
    """Return ``event_hooks`` recording outbound metrics for ``target``.

    ``target`` is a stable name for the callee (``"agent"``, ``"retrieval"``,
    ``"inference"``) so the series stays low-cardinality regardless of URL.
    """

    async def _on_request(request: Any) -> None:
        request.extensions[_START_KEY] = perf_counter()

    async def _on_response(response: Any) -> None:
        start = response.request.extensions.get(_START_KEY)
        method = response.request.method
        status_class = f"{response.status_code // 100}xx"
        http_client_requests_total().labels(
            service=service_name, method=method, target=target, status=status_class
        ).inc()
        if start is not None:
            http_client_request_duration_seconds().labels(
                service=service_name, method=method, target=target
            ).observe(perf_counter() - start)

    return {"request": [_on_request], "response": [_on_response]}
