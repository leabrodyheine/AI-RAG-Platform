"""Boot the four services on localhost with no Docker, for load testing.

Retrieval runs in its in-memory keyword mode (no ``DATABASE_URL``), inference
runs the deterministic backend, and the agent and gateway point at the other
local ports. The result is a CPU-only stack that answers ``POST /chat`` and
serves ``/metrics`` on ports 8000-8003 -- enough to run the load-test scenarios
and get reproducible baseline numbers.

    python scripts/run_local_stack.py                 # hold until Ctrl-C
    python scripts/run_local_stack.py --scenario cached   # apply that scenario's stack env
    python scripts/run_local_stack.py --run steady-state  # start, run the scenario, tear down

A scenario's ``env`` (for example the ``cached`` scenario's Postgres and Redis
URLs) is layered onto every service process; point those URLs at a stack you
started separately (``docker compose up postgres redis`` from ``infra/compose/``).
"""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# The offline ``evaluation`` package is intentionally not installed; put the repo
# root on the path so ``--scenario`` / ``--run`` can import it.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Keys that select the offline fallback. They are cleared from the child
# environment unless a scenario explicitly sets them.
_FALLBACK_KEYS = ("DATABASE_URL", "REDIS_URL")

_COMMON_ENV = {
    "OTEL_SDK_DISABLED": "true",
    "LOG_LEVEL": "WARNING",
    "PYTHONUNBUFFERED": "1",
}


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    app: str
    port_offset: int
    extra_env: dict[str, str]


# Started in this order; agent and gateway only build clients at startup, so
# they tolerate their upstreams not being ready yet.
SERVICES = (
    ServiceSpec(
        "inference", "inference_service.main:app", 3, {"INFERENCE_BACKEND": "deterministic"}
    ),
    ServiceSpec("retrieval", "retrieval_service.main:app", 2, {}),
    ServiceSpec("agent", "agent_service.main:app", 1, {}),
    ServiceSpec("gateway", "api_gateway.main:app", 0, {}),
)


def _host_url(base_port: int, offset: int) -> str:
    return f"http://127.0.0.1:{base_port + offset}"


def service_commands(
    base_port: int = 8000,
    *,
    scenario_env: dict[str, str] | None = None,
    parent_env: dict[str, str] | None = None,
) -> list[tuple[str, list[str], dict[str, str]]]:
    """Return ``(name, argv, env)`` for each service process."""
    parent = dict(parent_env if parent_env is not None else os.environ)
    scenario_env = scenario_env or {}
    ports = {spec.name: base_port + spec.port_offset for spec in SERVICES}

    wiring = {
        "agent": {
            "RETRIEVAL_SERVICE_URL": _host_url(base_port, 2),
            "INFERENCE_SERVICE_URL": _host_url(base_port, 3),
        },
        "gateway": {"AGENT_SERVICE_URL": _host_url(base_port, 1)},
    }

    commands: list[tuple[str, list[str], dict[str, str]]] = []
    for spec in SERVICES:
        env = {key: value for key, value in parent.items() if key not in _FALLBACK_KEYS}
        env.update(_COMMON_ENV)
        env.update(spec.extra_env)
        env.update(wiring.get(spec.name, {}))
        env.update(scenario_env)  # a scenario may put DATABASE_URL / REDIS_URL back
        argv = [
            sys.executable,
            "-m",
            "uvicorn",
            spec.app,
            "--host",
            "127.0.0.1",
            "--port",
            str(ports[spec.name]),
            "--log-level",
            "warning",
        ]
        commands.append((spec.name, argv, env))
    return commands


def _is_healthy(url: str, *, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_for_health(urls: list[str], *, timeout: float) -> list[str]:
    """Block until every URL answers /health; return the ones that never did."""
    deadline = time.monotonic() + timeout
    pending = list(urls)
    while pending and time.monotonic() < deadline:
        pending = [url for url in pending if not _is_healthy(url, timeout=2.0)]
        if pending:
            time.sleep(0.3)
    return pending


def _load_scenario_env(name: str | None, scenario_dir: Path) -> dict[str, str]:
    if not name:
        return {}
    from evaluation.performance.scenarios import load_scenario

    return dict(load_scenario(scenario_dir / f"{name}.json").env)


def _terminate(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for _, process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5.0
    for _, process in processes:
        remaining = max(0.0, deadline - time.monotonic())
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=remaining)
    for _, process in processes:
        if process.poll() is None:
            process.kill()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/run_local_stack.py",
        description="Start the four services on localhost for load testing.",
    )
    parser.add_argument("--base-port", type=int, default=8000, help="gateway port (default 8000)")
    parser.add_argument("--scenario", default=None, help="apply this scenario's stack env")
    parser.add_argument(
        "--scenario-dir",
        type=Path,
        default=_REPO_ROOT / "load-tests" / "scenarios",
    )
    parser.add_argument("--ready-timeout", type=float, default=40.0)
    parser.add_argument(
        "--run",
        metavar="SCENARIO",
        default=None,
        help="once ready, run this scenario with evaluation.performance.run, then tear down",
    )
    parser.add_argument(
        "--check-pass-fail",
        action="store_true",
        help="with --run, forward --check-pass-fail to the run harness",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenario_env = _load_scenario_env(args.scenario or args.run, args.scenario_dir)
    except Exception as error:  # noqa: BLE001 - surface any scenario problem plainly
        print(f"error: {error}", file=sys.stderr)
        return 2

    commands = service_commands(args.base_port, scenario_env=scenario_env)
    processes: list[tuple[str, subprocess.Popen]] = []
    print(f"starting {len(commands)} services (base port {args.base_port})")
    for name, cmd_argv, env in commands:
        processes.append((name, subprocess.Popen(cmd_argv, env=env, cwd=_REPO_ROOT)))

    urls = [_host_url(args.base_port, spec.port_offset) for spec in SERVICES]
    try:
        never_ready = wait_for_health(urls, timeout=args.ready_timeout)
        if never_ready:
            print(f"error: not ready within {args.ready_timeout}s: {never_ready}", file=sys.stderr)
            return 1
        print(f"stack ready: gateway on {_host_url(args.base_port, 0)}")

        if args.run:
            run_argv = [
                sys.executable,
                "-m",
                "evaluation.performance.run",
                args.run,
                "--host",
                _host_url(args.base_port, 0),
            ]
            if args.check_pass_fail:
                run_argv.append("--check-pass-fail")
            return subprocess.run(run_argv, cwd=_REPO_ROOT, check=False).returncode

        print("hold; Ctrl-C to stop")
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        print("stopping services")
        _terminate(processes)


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
