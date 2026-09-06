import pytest

from evaluation.performance.aggregate import (
    RequestRecord,
    aggregate_run,
    evaluate_pass_fail,
    summarize,
)
from evaluation.performance.scenarios import parse_scenario


def _scenario(**overrides) -> object:
    payload = {
        "schema": "load-scenario/v1",
        "name": "unit",
        "description": "aggregate unit scenario",
        "warmup": "10s",
        "stages": [{"duration": "50s", "users": 4, "spawn_rate": 4}],
        "pass_fail": {"max_error_rate": 0.1, "max_p95_ms": 500, "min_throughput_rps": 1.0},
    }
    payload.update(overrides)
    return parse_scenario(payload)


def _records(count: int, *, start: float, step: float, ms: float, name: str = "/chat [x]"):
    return [
        RequestRecord(offset_seconds=start + i * step, name=name, response_ms=ms, failed=False)
        for i in range(count)
    ]


def test_summarize_percentiles_and_throughput() -> None:
    records = [
        RequestRecord(offset_seconds=0, name="a", response_ms=float(v), failed=False)
        for v in range(1, 101)
    ]
    stats = summarize(records, window_seconds=10.0)
    assert stats.count == 100
    assert stats.p50_ms == 50
    assert stats.p95_ms == 95
    assert stats.p99_ms == 99
    assert stats.max_ms == 100
    assert stats.throughput_rps == pytest.approx(10.0)
    assert stats.error_rate == 0.0


def test_summarize_empty_is_all_zero() -> None:
    stats = summarize([], window_seconds=10.0)
    assert stats.count == 0
    assert stats.error_rate == 0.0
    assert stats.p95_ms == 0.0
    assert stats.throughput_rps == 0.0


def test_aggregate_run_drops_the_warmup_window() -> None:
    warm = _records(20, start=0.0, step=0.4, ms=999.0)  # inside the 10s warm-up
    scored = _records(60, start=10.0, step=0.5, ms=120.0)
    aggregate = aggregate_run(warm + scored, scenario=_scenario(), total_run_seconds=40.0)
    assert aggregate.total_requests == 80
    assert aggregate.scored_requests == 60
    assert aggregate.scored_window_seconds == pytest.approx(30.0)
    assert aggregate.overall.max_ms == 120.0  # the 999ms warm-up records are gone
    assert aggregate.overall.throughput_rps == pytest.approx(2.0)


def test_aggregate_run_splits_by_request_name() -> None:
    a = _records(10, start=12.0, step=1.0, ms=100.0, name="/chat [retrieval]")
    b = _records(5, start=12.0, step=1.0, ms=300.0, name="/chat [direct]")
    aggregate = aggregate_run(a + b, scenario=_scenario(), total_run_seconds=40.0)
    assert set(aggregate.by_name) == {"/chat [retrieval]", "/chat [direct]"}
    assert aggregate.by_name["/chat [direct]"].count == 5
    assert aggregate.by_name["/chat [retrieval]"].mean_ms == 100.0


def test_evaluate_pass_fail_flags_each_breach() -> None:
    scenario = _scenario()
    ok = summarize(_records(120, start=0.0, step=0.0, ms=200.0), window_seconds=30.0)
    assert evaluate_pass_fail(ok, scenario.pass_fail).passed

    slow = summarize(_records(120, start=0.0, step=0.0, ms=900.0), window_seconds=30.0)
    outcome = evaluate_pass_fail(slow, scenario.pass_fail)
    assert not outcome.passed
    assert [c.name for c in outcome.checks if not c.passed] == ["max_p95_ms"]


def test_evaluate_pass_fail_checks_error_rate_and_throughput() -> None:
    scenario = _scenario()
    failing = [
        RequestRecord(offset_seconds=0.0, name="a", response_ms=50.0, failed=i % 2 == 0)
        for i in range(10)
    ]
    outcome = evaluate_pass_fail(summarize(failing, window_seconds=100.0), scenario.pass_fail)
    breached = {c.name for c in outcome.checks if not c.passed}
    assert breached == {"max_error_rate", "min_throughput_rps"}


def test_min_throughput_check_is_skipped_when_unset() -> None:
    scenario = _scenario(
        pass_fail={"max_error_rate": 0.1, "max_p95_ms": 500}
    )
    stats = summarize(_records(3, start=0.0, step=0.0, ms=10.0), window_seconds=100.0)
    outcome = evaluate_pass_fail(stats, scenario.pass_fail)
    assert [c.name for c in outcome.checks] == ["max_error_rate", "max_p95_ms"]
    assert outcome.passed
