from prometheus_client import CollectorRegistry
from rag_observability import metrics


def test_metric_factories_return_the_same_registered_object() -> None:
    first = metrics.http_server_requests_total()
    second = metrics.http_server_requests_total()
    assert first is second


def test_render_latest_exposes_observed_series_from_the_dedicated_registry() -> None:
    metrics.retrieval_cache_events_total().labels(service="retrieval", result="hit").inc()
    metrics.inference_tokens_total().labels(
        service="inference", backend="deterministic", model="m", kind="completion"
    ).inc(7)

    body, content_type = metrics.render_latest()
    text = body.decode()

    assert isinstance(metrics.REGISTRY, CollectorRegistry)
    assert "text/plain" in content_type
    assert 'retrieval_cache_events_total{result="hit",service="retrieval"} 1.0' in text
    assert 'inference_tokens_total{backend="deterministic",kind="completion"' in text


def test_expected_series_names_are_registered() -> None:
    metrics.http_server_request_duration_seconds()
    metrics.retrieval_query_duration_seconds()
    metrics.inference_generation_duration_seconds()

    names = set(metrics.REGISTRY._names_to_collectors)  # type: ignore[attr-defined]
    assert "http_server_request_duration_seconds" in names
    assert "retrieval_query_duration_seconds_bucket" in names
    assert "inference_generation_duration_seconds_sum" in names
