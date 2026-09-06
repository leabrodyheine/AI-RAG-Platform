"""Command line entry point: ``python -m evaluation.performance.run``.

Drives one load-test scenario against a running stack with Locust embedded in
this process, scores the post-warm-up window, and writes a JSON report and a
Markdown one. The stack must already be up -- the Compose stack, or the offline
fallback stack started by ``scripts/run_local_stack.py``.

    python -m evaluation.performance.run steady-state --host http://localhost:8000

Raw reports default to ``load-tests/results/`` (git-ignored); only hand-picked
summaries are committed.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

from evaluation.performance.aggregate import RequestRecord, aggregate_run
from evaluation.performance.report import build_report, render_markdown
from evaluation.performance.scenarios import (
    DEFAULT_SCENARIO_DIR,
    Scenario,
    ScenarioError,
    load_scenario,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCUSTFILE = _REPO_ROOT / "load-tests" / "locustfile.py"
DEFAULT_RESULT_DIR = _REPO_ROOT / "load-tests" / "results"


def _load_user_class() -> type:
    """Import ``ChatUser`` from the (hyphenated, non-package) load-tests dir."""
    spec = importlib.util.spec_from_file_location("rag_load_locustfile", _LOCUSTFILE)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot import {_LOCUSTFILE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ChatUser


def _question_set_path(scenario: Scenario) -> str:
    candidate = Path(scenario.question_set)
    if not candidate.is_absolute():
        candidate = _REPO_ROOT / candidate
    return str(candidate)


def execute_scenario(scenario: Scenario, *, host: str) -> tuple[list[RequestRecord], float]:
    """Run the scenario's stages in order and collect one record per request."""
    import gevent
    from locust.env import Environment

    os.environ["LOAD_QUESTION_SET"] = _question_set_path(scenario)
    os.environ["LOAD_WAIT_MIN"] = repr(scenario.wait_min)
    os.environ["LOAD_WAIT_MAX"] = repr(scenario.wait_max)

    user_class = _load_user_class()
    env = Environment(user_classes=[user_class], host=host)
    records: list[RequestRecord] = []
    started = time.monotonic()

    def _on_request(name: str, response_time: float, exception: object, **_: object) -> None:
        records.append(
            RequestRecord(
                offset_seconds=time.monotonic() - started,
                name=name,
                response_ms=float(response_time or 0.0),
                failed=exception is not None,
            )
        )

    env.events.request.add_listener(_on_request)
    runner = env.create_local_runner()
    try:
        for stage in scenario.stages:
            runner.start(stage.users, spawn_rate=stage.spawn_rate)
            gevent.sleep(stage.duration_seconds)
    finally:
        runner.quit()
    return records, time.monotonic() - started


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation.performance.run",
        description="Run one load-test scenario and write its reports.",
    )
    parser.add_argument("scenario", help="scenario name (file stem under the scenario dir)")
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--scenario-dir", type=Path, default=DEFAULT_SCENARIO_DIR)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument(
        "--check-pass-fail",
        action="store_true",
        help="exit 1 when the scenario's pass_fail thresholds are breached",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the output file paths")
    return parser


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    import json

    args = build_parser().parse_args(argv)
    try:
        scenario = load_scenario(Path(args.scenario_dir) / f"{args.scenario}.json")
    except ScenarioError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE

    records, elapsed = execute_scenario(scenario, host=args.host)
    aggregate = aggregate_run(records, scenario=scenario, total_run_seconds=elapsed)
    report = build_report(aggregate, scenario=scenario, host=args.host)

    json_out = args.json_out or DEFAULT_RESULT_DIR / f"{scenario.name}-latest.json"
    markdown_out = args.markdown_out or DEFAULT_RESULT_DIR / f"{scenario.name}-latest.md"
    _write(json_out, json.dumps(report, indent=2, sort_keys=True))
    markdown = render_markdown(report)
    _write(markdown_out, markdown)

    if args.quiet:
        print(json_out)
        print(markdown_out)
    else:
        print(markdown)
        print(f"\nwrote {json_out}")
        print(f"wrote {markdown_out}")

    if args.check_pass_fail and not aggregate.pass_fail.passed:
        print("\nperformance gate FAILED", file=sys.stderr)
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
