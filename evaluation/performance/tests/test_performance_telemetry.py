from evaluation.performance.telemetry import (
    TelemetryRecorder,
    parse_metrics_text,
)

_H = "http_server_request_duration_seconds"
_METRICS_PAGE = f"""\
# HELP {_H} Wall-clock duration of inbound HTTP requests.
# TYPE {_H} histogram
{_H}_bucket{{service="gw",method="POST",route="/chat",le="0.5"}} 8
{_H}_bucket{{service="gw",method="POST",route="/chat",le="+Inf"}} 10
{_H}_sum{{service="gw",method="POST",route="/chat"}} 1.5
{_H}_count{{service="gw",method="POST",route="/chat"}} 10
{_H}_created{{service="gw",method="POST",route="/chat"}} 1.7e9
# TYPE retrieval_query_duration_seconds histogram
retrieval_query_duration_seconds_sum{{service="retrieval",path="memory"}} 0.4
retrieval_query_duration_seconds_count{{service="retrieval",path="memory"}} 20
# TYPE retrieval_cache_events_total counter
retrieval_cache_events_total{{service="retrieval",result="bypass"}} 20.0
retrieval_cache_events_total_created{{service="retrieval",result="bypass"}} 1.7e9
# an unrelated family the parser should ignore
process_resident_memory_bytes 1.234e8
"""


def test_parse_metrics_text_pulls_the_needed_families_only() -> None:
    histograms, counters = parse_metrics_text(_METRICS_PAGE)

    http_key = (
        "http_server_request_duration_seconds",
        (("method", "POST"), ("route", "/chat"), ("service", "gw")),
    )
    assert histograms[http_key] == [1.5, 10.0]

    retr_key = ("retrieval_query_duration_seconds", (("path", "memory"), ("service", "retrieval")))
    assert histograms[retr_key] == [0.4, 20.0]

    cache_key = ("retrieval_cache_events_total", (("result", "bypass"), ("service", "retrieval")))
    assert counters[cache_key] == 20.0

    # No bucket lines, no _created lines, no unrelated families leaked in.
    assert all(not name.endswith(("_bucket", "_created")) for name, _ in histograms)
    assert not any("process_resident_memory" in name for name, _ in counters)


def test_summary_windows_histogram_means_and_counter_deltas() -> None:
    from evaluation.performance.telemetry import _Scrape

    http_labels = (("method", "POST"), ("route", "/chat"), ("service", "gw"))
    retr_labels = (("path", "memory"), ("service", "retrieval"))
    cache_labels = (("result", "bypass"), ("service", "retrieval"))

    start = _Scrape(
        0.0,
        {
            ("http_server_request_duration_seconds", http_labels): [1.5, 10.0],
            ("retrieval_query_duration_seconds", retr_labels): [0.4, 20.0],
        },
        {("retrieval_cache_events_total", cache_labels): 20.0},
    )
    warm = _Scrape(1.0, dict(start.histograms), dict(start.counters))  # dropped by warm-up
    end = _Scrape(
        30.0,
        {
            ("http_server_request_duration_seconds", http_labels): [13.5, 110.0],
            ("retrieval_query_duration_seconds", retr_labels): [10.4, 120.0],
        },
        {("retrieval_cache_events_total", cache_labels): 120.0},
    )

    recorder = TelemetryRecorder(endpoints=[])
    recorder._scrapes = [start, warm, end]
    server = recorder.summary(warmup_seconds=3.0)["server_metrics"]

    http = server["http_server_request_duration_seconds"]["method=POST,route=/chat"]
    assert http["count"] == 100
    assert http["mean_ms"] == 120.0  # (13.5 - 1.5) / (110 - 10) * 1000

    assert server["retrieval_query_duration_seconds"]["path=memory"]["count"] == 100
    assert server["retrieval_cache_events_total"]["result=bypass"] == 100.0


def test_summary_reports_no_gpu_and_no_host_without_samples() -> None:
    summary = TelemetryRecorder(endpoints=[]).summary(warmup_seconds=0.0)
    assert summary["gpu"] == {"available": False}
    assert summary["host"] == {}
    assert summary["scrapes"] == 0


def test_collect_host_records_cpu_and_memory() -> None:
    recorder = TelemetryRecorder(endpoints=[])
    recorder.start()
    recorder.stop()
    recorder._collect_host(1.0)
    recorder._collect_host(2.0)
    summary = recorder.summary(warmup_seconds=0.0)
    assert 0.0 <= summary["host"]["cpu_percent_mean"] <= 100.0
    assert summary["host"]["mem_used_mb_max"] > 0


def test_unreachable_endpoint_is_recorded_not_raised() -> None:
    recorder = TelemetryRecorder(endpoints=["http://127.0.0.1:1/metrics"], timeout=0.2)
    recorder._collect_metrics(0.0)
    assert recorder.summary(warmup_seconds=0.0)["endpoints"] == {
        "http://127.0.0.1:1/metrics": "unreachable"
    }
