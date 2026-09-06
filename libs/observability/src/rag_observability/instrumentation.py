"""``instrument_app`` — the one call each service makes to wire observability.

It configures JSON logging and tracing for the service, turns on OpenTelemetry
for inbound requests and outbound httpx calls, and adds a middleware that:

- resolves the request id from ``X-Request-ID`` (or mints one) and binds it so
  logs and spans carry it,
- records ``http_server_*`` Prometheus metrics keyed by the route template,
- emits one structured access-log line per request,
- echoes ``X-Request-ID`` back on the response.

It also mounts ``GET /metrics``. Health and metrics endpoints are excluded from
the access log and request metrics so they do not drown out real traffic.
"""

import logging
from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import FastAPI, Request, Response
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

from rag_observability.context import (
    REQUEST_ID_HEADER,
    bind_request_id,
    resolve_request_id,
)
from rag_observability.logging import configure_logging
from rag_observability.metrics import (
    http_server_request_duration_seconds,
    http_server_requests_total,
    render_latest,
)
from rag_observability.tracing import configure_tracing

_DEFAULT_QUIET_ROUTES = ("/metrics", "/health", "/ready")
_httpx_instrumented = False


def instrument_app(
    app: FastAPI,
    service_name: str,
    *,
    metrics_path: str = "/metrics",
    quiet_routes: tuple[str, ...] = _DEFAULT_QUIET_ROUTES,
) -> None:
    configure_logging(service_name)
    configure_tracing(service_name)

    access_log = logging.getLogger(f"{service_name}.access")

    @app.middleware("http")
    async def _observe(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        bind_request_id(request_id)
        request.state.request_id = request_id

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("rag.request_id", request_id)

        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _record(service_name, request.method, _route_of(request), 500, started)
            access_log.exception(
                "request failed",
                extra={"method": request.method, "route": _route_of(request)},
            )
            raise

        duration_s = perf_counter() - started
        route = _route_of(request)
        response.headers.setdefault(REQUEST_ID_HEADER, request_id)

        if route not in quiet_routes:
            _record(service_name, request.method, route, response.status_code, started)
            access_log.info(
                "request handled",
                extra={
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(duration_s * 1000, 2),
                },
            )
        return response

    _instrument_libraries(app)

    @app.get(metrics_path, include_in_schema=False)
    async def metrics_endpoint() -> Response:
        body, content_type = render_latest()
        return Response(content=body, media_type=content_type)

    app.state.observability_service = service_name


def _instrument_libraries(app: FastAPI) -> None:
    global _httpx_instrumented
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=trace.get_tracer_provider(),
        excluded_urls="/metrics,/health,/ready",
    )
    if not _httpx_instrumented:
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True


def _route_of(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"


def _record(service: str, method: str, route: str, status_code: int, started: float) -> None:
    status_class = f"{status_code // 100}xx"
    http_server_requests_total().labels(
        service=service, method=method, route=route, status=status_class
    ).inc()
    http_server_request_duration_seconds().labels(
        service=service, method=method, route=route
    ).observe(perf_counter() - started)
