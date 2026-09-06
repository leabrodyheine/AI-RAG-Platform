import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "run_local_stack.py"
_spec = importlib.util.spec_from_file_location("run_local_stack", _MODULE_PATH)
assert _spec and _spec.loader
run_local_stack = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run_local_stack  # dataclasses needs the module registered
_spec.loader.exec_module(run_local_stack)


def _by_name(commands):
    return {name: (argv, env) for name, argv, env in commands}


def test_service_commands_wire_localhost_urls() -> None:
    commands = _by_name(run_local_stack.service_commands(8000, parent_env={}))
    assert set(commands) == {"inference", "retrieval", "agent", "gateway"}

    agent_env = commands["agent"][1]
    assert agent_env["RETRIEVAL_SERVICE_URL"] == "http://127.0.0.1:8002"
    assert agent_env["INFERENCE_SERVICE_URL"] == "http://127.0.0.1:8003"
    assert commands["gateway"][1]["AGENT_SERVICE_URL"] == "http://127.0.0.1:8001"

    gateway_argv = commands["gateway"][0]
    assert "api_gateway.main:app" in gateway_argv
    assert gateway_argv[gateway_argv.index("--port") + 1] == "8000"
    assert gateway_argv[1:3] == ["-m", "uvicorn"]


def test_base_port_shifts_every_service() -> None:
    commands = _by_name(run_local_stack.service_commands(9100, parent_env={}))
    ports = {
        name: argv[argv.index("--port") + 1] for name, (argv, _) in commands.items()
    }
    assert ports == {
        "gateway": "9100",
        "agent": "9101",
        "retrieval": "9102",
        "inference": "9103",
    }


def test_fallback_keys_are_cleared_unless_a_scenario_sets_them() -> None:
    parent = {"DATABASE_URL": "postgresql://inherited", "REDIS_URL": "redis://inherited"}

    plain = _by_name(run_local_stack.service_commands(8000, parent_env=parent))
    assert "DATABASE_URL" not in plain["retrieval"][1]
    assert "REDIS_URL" not in plain["retrieval"][1]

    cached = _by_name(
        run_local_stack.service_commands(
            8000,
            parent_env=parent,
            scenario_env={"DATABASE_URL": "postgresql://scenario", "REDIS_URL": "redis://scenario"},
        )
    )
    assert cached["retrieval"][1]["DATABASE_URL"] == "postgresql://scenario"
    assert cached["retrieval"][1]["REDIS_URL"] == "redis://scenario"


def test_common_env_disables_otel_and_quiets_logging() -> None:
    commands = _by_name(run_local_stack.service_commands(8000, parent_env={}))
    for _, env in commands.values():
        assert env["OTEL_SDK_DISABLED"] == "true"
        assert env["LOG_LEVEL"] == "WARNING"


def test_load_scenario_env_reads_the_committed_cached_scenario() -> None:
    scenario_dir = _MODULE_PATH.parents[1] / "load-tests" / "scenarios"
    env = run_local_stack._load_scenario_env("cached", scenario_dir)
    assert "REDIS_URL" in env
    assert run_local_stack._load_scenario_env(None, scenario_dir) == {}
