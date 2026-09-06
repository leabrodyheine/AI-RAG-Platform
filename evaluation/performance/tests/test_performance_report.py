import json
from datetime import UTC, datetime

from evaluation.performance.aggregate import RequestRecord, aggregate_run
from evaluation.performance.report import REPORT_SCHEMA, build_report, render_markdown
from evaluation.performance.scenarios import parse_scenario


def _aggregate(*, failed: bool = False):
    scenario = parse_scenario(
        {
            "schema": "load-scenario/v1",
            "name": "steady-state",
            "description": "baseline scenario for the report test",
            "warmup": "5s",
            "stages": [{"duration": "25s", "users": 8, "spawn_rate": 4}],
            "pass_fail": {"max_error_rate": 0.01, "max_p95_ms": 250, "min_throughput_rps": 1.0},
        }
    )
    ms = 900.0 if failed else 120.0
    records = [
        RequestRecord(offset_seconds=6.0 + i * 0.5, name="/chat [retrieval]", response_ms=ms,
                      failed=False)
        for i in range(40)
    ]
    return aggregate_run(records, scenario=scenario, total_run_seconds=30.0), scenario


def test_build_report_shape_and_reproducibility_block() -> None:
    aggregate, scenario = _aggregate()
    report = build_report(
        aggregate,
        scenario=scenario,
        host="http://localhost:8000",
        commit="abc123",
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    assert report["schema"] == REPORT_SCHEMA
    assert report["run"]["commit"] == "abc123"
    assert report["run"]["generated_at"] == "2026-01-02T03:04:05Z"
    assert report["run"]["scenario"]["stages"][0]["users"] == 8
    assert report["run"]["scenario"]["pass_fail"]["max_p95_ms"] == 250
    assert report["telemetry"] is None
    assert report["metrics"]["overall"]["count"] == 40
    assert report["pass_fail"]["passed"] is True


def test_report_json_is_pretty_printed_and_sorted() -> None:
    aggregate, scenario = _aggregate()
    report = build_report(aggregate, scenario=scenario, host="http://localhost:8000")
    text = json.dumps(report, indent=2, sort_keys=True)
    assert text.startswith("{\n")
    assert json.loads(text) == report


def test_render_markdown_reports_pass_and_fail() -> None:
    ok_aggregate, scenario = _aggregate()
    ok_md = render_markdown(build_report(ok_aggregate, scenario=scenario, host="h"))
    assert "**Status:** PASS" in ok_md
    assert "steady-state" in ok_md
    assert "/chat [retrieval]" in ok_md

    bad_aggregate, scenario = _aggregate(failed=True)
    bad_md = render_markdown(build_report(bad_aggregate, scenario=scenario, host="h"))
    assert "**Status:** FAIL" in bad_md
    assert "max_p95_ms" in bad_md


def test_render_markdown_notes_dropped_warmup() -> None:
    aggregate, scenario = _aggregate()
    md = render_markdown(build_report(aggregate, scenario=scenario, host="h"))
    assert "Warm-up dropped: 5.000s" in md
    assert "scored 40 of 40 requests" in md
