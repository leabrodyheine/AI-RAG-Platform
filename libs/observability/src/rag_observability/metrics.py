"""The Prometheus series every service can expose on ``/metrics``.

All metrics live in one dedicated :class:`CollectorRegistry` (not the global
default) so that importing several service apps into a single test process does
not raise duplicate-registration errors, and so ``/metrics`` shows exactly the
series defined here. Metric objects are created once and looked up by name.

Naming follows Prometheus conventions: ``_total`` counters, ``_seconds``
histograms, a ``service`` label on everything so one scrape target per service
stays readable in Grafana.
"""

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client import generate_latest as _generate_latest

REGISTRY = CollectorRegistry()

_LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
)

_metrics: dict[str, Counter | Histogram] = {}


def _counter(name: str, doc: str, labels: tuple[str, ...]) -> Counter:
    if name not in _metrics:
        _metrics[name] = Counter(name, doc, labels, registry=REGISTRY)
    return _metrics[name]  # type: ignore[return-value]


def _histogram(name: str, doc: str, labels: tuple[str, ...]) -> Histogram:
    if name not in _metrics:
        _metrics[name] = Histogram(
            name, doc, labels, registry=REGISTRY, buckets=_LATENCY_BUCKETS
        )
    return _metrics[name]  # type: ignore[return-value]


# --- Inbound HTTP (served by this service) ---------------------------------

def http_server_requests_total() -> Counter:
    return _counter(
        "http_server_requests_total",
        "Inbound HTTP requests handled, by route and status class.",
        ("service", "method", "route", "status"),
    )


def http_server_request_duration_seconds() -> Histogram:
    return _histogram(
        "http_server_request_duration_seconds",
        "Wall-clock duration of inbound HTTP requests.",
        ("service", "method", "route"),
    )


# --- Outbound HTTP (this service calling another) --------------------------

def http_client_requests_total() -> Counter:
    return _counter(
        "http_client_requests_total",
        "Outbound HTTP requests made to another service, by target and status.",
        ("service", "method", "target", "status"),
    )


def http_client_request_duration_seconds() -> Histogram:
    return _histogram(
        "http_client_request_duration_seconds",
        "Wall-clock duration of outbound HTTP requests.",
        ("service", "method", "target"),
    )


# --- Retrieval cache -------------------------------------------------------

def retrieval_cache_events_total() -> Counter:
    return _counter(
        "retrieval_cache_events_total",
        "Retrieval cache outcomes (hit, miss, bypass).",
        ("service", "result"),
    )


def retrieval_query_duration_seconds() -> Histogram:
    return _histogram(
        "retrieval_query_duration_seconds",
        "Duration of a retrieval query, by the path that served it.",
        ("service", "path"),
    )


# --- Inference generation ------------------------------------------------

def inference_generation_duration_seconds() -> Histogram:
    return _histogram(
        "inference_generation_duration_seconds",
        "Duration of one generation call, by backend and model.",
        ("service", "backend", "model"),
    )


def inference_time_to_first_token_seconds() -> Histogram:
    return _histogram(
        "inference_time_to_first_token_seconds",
        "Time to first token for streaming-capable backends.",
        ("service", "backend", "model"),
    )


def inference_tokens_total() -> Counter:
    return _counter(
        "inference_tokens_total",
        "Tokens accounted by the inference service, by kind (prompt, completion).",
        ("service", "backend", "model", "kind"),
    )


def render_latest() -> tuple[bytes, str]:
    """Return the ``(body, content_type)`` for a ``/metrics`` response."""
    return _generate_latest(REGISTRY), CONTENT_TYPE_LATEST
