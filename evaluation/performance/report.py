"""Assemble a scored run into a machine-readable report and a readable one.

``build_report`` returns a JSON-serialisable dict: a ``run`` block that records
what would be needed to reproduce the numbers (commit, Python, host, the full
scenario definition) plus the aggregate metrics and the pass/fail outcome.
``render_markdown`` turns that into the report a person reads.

``telemetry`` is passed straight through; the server-metric and host-resource
sampler fills it in, and it stays ``None`` for a client-only run.
"""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime

from evaluation.performance.aggregate import ScenarioAggregate
from evaluation.performance.scenarios import Scenario

REPORT_SCHEMA = "perf-report/v1"


def resolve_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _scenario_dict(scenario: Scenario) -> dict:
    return {
        "name": scenario.name,
        "description": scenario.description,
        "question_set": scenario.question_set,
        "wait_min": scenario.wait_min,
        "wait_max": scenario.wait_max,
        "warmup_seconds": scenario.warmup_seconds,
        "run_time_seconds": scenario.run_time_seconds,
        "peak_users": scenario.peak_users,
        "stages": [
            {
                "duration_seconds": stage.duration_seconds,
                "users": stage.users,
                "spawn_rate": stage.spawn_rate,
            }
            for stage in scenario.stages
        ],
        "env": dict(scenario.env),
        "pass_fail": {
            "max_error_rate": scenario.pass_fail.max_error_rate,
            "max_p95_ms": scenario.pass_fail.max_p95_ms,
            "min_throughput_rps": scenario.pass_fail.min_throughput_rps,
        },
    }


def build_report(
    aggregate: ScenarioAggregate,
    *,
    scenario: Scenario,
    host: str,
    commit: str | None = None,
    generated_at: datetime | None = None,
    telemetry: dict | None = None,
) -> dict:
    moment = (generated_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "schema": REPORT_SCHEMA,
        "run": {
            "generated_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit": commit if commit is not None else resolve_commit(),
            "python_version": platform.python_version(),
            "host": host,
            "scenario": _scenario_dict(scenario),
        },
        "metrics": aggregate.as_dict(),
        "telemetry": telemetry,
        "pass_fail": aggregate.pass_fail.as_dict(),
    }


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    if value is None:
        return "-"
    return str(value)


def _stats_row(label: str, stats: dict) -> str:
    return (
        f"| {label} | {stats['count']} | {_fmt(stats['throughput_rps'])} | "
        f"{_fmt(stats['error_rate'])} | {_fmt(stats['p50_ms'])} | {_fmt(stats['p90_ms'])} | "
        f"{_fmt(stats['p95_ms'])} | {_fmt(stats['p99_ms'])} | {_fmt(stats['max_ms'])} |"
    )


def render_markdown(report: dict) -> str:
    run = report["run"]
    scenario = run["scenario"]
    metrics = report["metrics"]
    pass_fail = report["pass_fail"]

    lines: list[str] = []
    lines.append("# Performance run report")
    lines.append("")
    lines.append(f"**Status:** {'PASS' if pass_fail['passed'] else 'FAIL'}")
    lines.append("")

    lines.append("## Run")
    lines.append("")
    lines.append(f"- Generated: `{run['generated_at']}`")
    lines.append(f"- Commit: `{run['commit']}`")
    lines.append(f"- Python: `{run['python_version']}`")
    lines.append(f"- Host: `{run['host']}`")
    lines.append(f"- Scenario: `{scenario['name']}` — {scenario['description']}")
    stage_text = ", ".join(
        f"{stage['users']}u/{_fmt(stage['duration_seconds'])}s" for stage in scenario["stages"]
    )
    lines.append(f"- Stages: {stage_text}")
    lines.append(
        f"- Warm-up dropped: {_fmt(metrics['warmup_seconds'])}s of "
        f"{_fmt(metrics['warmup_seconds'] + metrics['scored_window_seconds'])}s; "
        f"scored {metrics['scored_requests']} of {metrics['total_requests']} requests"
    )
    if scenario["env"]:
        env_text = ", ".join(f"{key}={value}" for key, value in sorted(scenario["env"].items()))
        lines.append(f"- Stack env: {env_text}")
    lines.append("")

    lines.append("## Latency and throughput")
    lines.append("")
    lines.append(
        "| Group | Requests | RPS | Error rate | p50 ms | p90 ms | p95 ms | p99 ms | max ms |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    lines.append(_stats_row("overall", metrics["overall"]))
    for name, stats in metrics["by_name"].items():
        lines.append(_stats_row(name, stats))
    lines.append("")

    lines.append("## Pass/fail")
    lines.append("")
    lines.append("| Check | Threshold | Observed | Result |")
    lines.append("| --- | --- | --- | --- |")
    for check in pass_fail["checks"]:
        lines.append(
            f"| {check['name']} | {_fmt(check['threshold'])} | {_fmt(check['observed'])} | "
            f"{'ok' if check['passed'] else 'FAIL'} |"
        )
    lines.append("")

    telemetry = report.get("telemetry")
    if telemetry:
        lines.extend(_render_telemetry(telemetry))

    return "\n".join(lines)


def _render_telemetry(telemetry: dict) -> list[str]:
    lines = ["## Server and host telemetry", ""]

    host = telemetry.get("host") or {}
    if host:
        lines.append(
            f"- CPU: {_fmt(host.get('cpu_percent_mean'))}% mean, "
            f"{_fmt(host.get('cpu_percent_max'))}% max"
        )
        lines.append(
            f"- Memory: {_fmt(host.get('mem_percent_mean'))}% mean, "
            f"{_fmt(host.get('mem_used_mb_max'))} MB peak used"
        )
    gpu = telemetry.get("gpu") or {}
    if gpu.get("available"):
        lines.append(
            f"- GPU ({gpu.get('name')}): {_fmt(gpu.get('util_percent_mean'))}% mean util, "
            f"{_fmt(gpu.get('mem_used_mb_max'))} MB peak used"
        )
    else:
        lines.append("- GPU: not present on this host")
    lines.append("")

    server = telemetry.get("server_metrics") or {}
    if server:
        lines.append("| Family | Labels | Count | Mean ms / delta |")
        lines.append("| --- | --- | --- | --- |")
        for family, groups in server.items():
            for label_key, value in groups.items():
                if isinstance(value, dict):
                    lines.append(
                        f"| {family} | {label_key} | {value['count']} | {_fmt(value['mean_ms'])} |"
                    )
                else:
                    lines.append(f"| {family} | {label_key} | - | {_fmt(value)} |")
        lines.append("")

    return lines
