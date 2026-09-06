"""Convenience recorders for the domain metrics services emit by hand.

The HTTP metrics are filled in by :func:`instrument_app`; these cover the
retrieval-cache and inference series, which only the service that owns the work
can measure. Each function is a thin wrapper over the metric factories in
:mod:`rag_observability.metrics` so call sites stay readable.
"""

from rag_observability.metrics import (
    inference_generation_duration_seconds,
    inference_time_to_first_token_seconds,
    inference_tokens_total,
    retrieval_cache_events_total,
    retrieval_query_duration_seconds,
)

CACHE_RESULTS = ("hit", "miss", "bypass")


def record_cache_event(service: str, result: str) -> None:
    """Count one retrieval-cache outcome (``hit``, ``miss`` or ``bypass``)."""
    retrieval_cache_events_total().labels(service=service, result=result).inc()


def observe_retrieval_query(service: str, path: str, seconds: float) -> None:
    """Record how long a retrieval query took, by the path that served it."""
    retrieval_query_duration_seconds().labels(service=service, path=path).observe(seconds)


def record_generation(
    service: str,
    backend: str,
    model: str,
    *,
    duration_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
    time_to_first_token_seconds: float | None = None,
) -> None:
    """Record one generation call's duration, token counts, and (if the backend
    streams) its time to first token."""
    labels = {"service": service, "backend": backend, "model": model}
    inference_generation_duration_seconds().labels(**labels).observe(duration_seconds)
    inference_tokens_total().labels(**labels, kind="prompt").inc(prompt_tokens)
    inference_tokens_total().labels(**labels, kind="completion").inc(completion_tokens)
    if time_to_first_token_seconds is not None:
        inference_time_to_first_token_seconds().labels(**labels).observe(
            time_to_first_token_seconds
        )
