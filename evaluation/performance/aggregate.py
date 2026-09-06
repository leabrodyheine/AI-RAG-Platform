"""Turn a stream of completed requests into a scored aggregate.

The run harness records one :class:`RequestRecord` per completed chat request,
timestamped by its offset from the start of the run. ``aggregate_run`` drops the
warm-up window, then reduces the remainder to latency percentiles, throughput,
and error rate -- overall and split by request name -- and checks the
scenario's ``pass_fail`` thresholds against the overall figures.

Nothing here imports Locust, so it can be exercised with synthetic records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import fmean

from evaluation.performance.scenarios import PassFail, Scenario

_MS = 3
_RATE = 5


@dataclass(frozen=True)
class RequestRecord:
    """One completed request, timed from the start of the run."""

    offset_seconds: float
    name: str
    response_ms: float
    failed: bool


def _percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (the convention Locust reports), 0 <= q <= 100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil(q / 100 * len(ordered)) - 1)
    return ordered[rank]


@dataclass(frozen=True)
class LatencyStats:
    count: int
    failures: int
    error_rate: float
    throughput_rps: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    min_ms: float
    max_ms: float
    mean_ms: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "failures": self.failures,
            "error_rate": round(self.error_rate, _RATE),
            "throughput_rps": round(self.throughput_rps, _MS),
            "p50_ms": round(self.p50_ms, _MS),
            "p90_ms": round(self.p90_ms, _MS),
            "p95_ms": round(self.p95_ms, _MS),
            "p99_ms": round(self.p99_ms, _MS),
            "min_ms": round(self.min_ms, _MS),
            "max_ms": round(self.max_ms, _MS),
            "mean_ms": round(self.mean_ms, _MS),
        }


def summarize(records: list[RequestRecord], *, window_seconds: float) -> LatencyStats:
    """Reduce a set of records to latency stats; ``window_seconds`` sets throughput."""
    count = len(records)
    if count == 0:
        return LatencyStats(0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    latencies = [r.response_ms for r in records]
    failures = sum(1 for r in records if r.failed)
    return LatencyStats(
        count=count,
        failures=failures,
        error_rate=failures / count,
        throughput_rps=count / window_seconds if window_seconds > 0 else 0.0,
        p50_ms=_percentile(latencies, 50),
        p90_ms=_percentile(latencies, 90),
        p95_ms=_percentile(latencies, 95),
        p99_ms=_percentile(latencies, 99),
        min_ms=min(latencies),
        max_ms=max(latencies),
        mean_ms=fmean(latencies),
    )


@dataclass(frozen=True)
class PassFailCheck:
    name: str
    threshold: float
    observed: float
    passed: bool

    def as_dict(self) -> dict[str, float | str | bool]:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "observed": round(self.observed, _MS),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class PassFailOutcome:
    passed: bool
    checks: tuple[PassFailCheck, ...]

    def as_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "checks": [c.as_dict() for c in self.checks]}


def evaluate_pass_fail(stats: LatencyStats, pass_fail: PassFail) -> PassFailOutcome:
    checks = [
        PassFailCheck(
            "max_error_rate",
            pass_fail.max_error_rate,
            stats.error_rate,
            stats.error_rate <= pass_fail.max_error_rate,
        ),
        PassFailCheck(
            "max_p95_ms",
            pass_fail.max_p95_ms,
            stats.p95_ms,
            stats.p95_ms <= pass_fail.max_p95_ms,
        ),
    ]
    if pass_fail.min_throughput_rps is not None:
        checks.append(
            PassFailCheck(
                "min_throughput_rps",
                pass_fail.min_throughput_rps,
                stats.throughput_rps,
                stats.throughput_rps >= pass_fail.min_throughput_rps,
            )
        )
    return PassFailOutcome(passed=all(check.passed for check in checks), checks=tuple(checks))


@dataclass(frozen=True)
class ScenarioAggregate:
    scenario_name: str
    total_requests: int
    scored_requests: int
    warmup_seconds: float
    scored_window_seconds: float
    overall: LatencyStats
    by_name: dict[str, LatencyStats]
    pass_fail: PassFailOutcome

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario_name": self.scenario_name,
            "total_requests": self.total_requests,
            "scored_requests": self.scored_requests,
            "warmup_seconds": round(self.warmup_seconds, _MS),
            "scored_window_seconds": round(self.scored_window_seconds, _MS),
            "overall": self.overall.as_dict(),
            "by_name": {name: stats.as_dict() for name, stats in self.by_name.items()},
            "pass_fail": self.pass_fail.as_dict(),
        }


def aggregate_run(
    records: list[RequestRecord],
    *,
    scenario: Scenario,
    total_run_seconds: float,
) -> ScenarioAggregate:
    """Drop the warm-up window and score the rest against the scenario."""
    warmup = scenario.warmup_seconds
    scored = [record for record in records if record.offset_seconds >= warmup]
    window = max(total_run_seconds - warmup, 0.0)
    overall = summarize(scored, window_seconds=window)
    names = sorted({record.name for record in scored})
    by_name = {
        name: summarize([r for r in scored if r.name == name], window_seconds=window)
        for name in names
    }
    return ScenarioAggregate(
        scenario_name=scenario.name,
        total_requests=len(records),
        scored_requests=len(scored),
        warmup_seconds=warmup,
        scored_window_seconds=window,
        overall=overall,
        by_name=by_name,
        pass_fail=evaluate_pass_fail(overall, scenario.pass_fail),
    )
