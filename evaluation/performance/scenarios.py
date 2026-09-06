"""Load-test scenario definitions: schema, loader, and validation.

A scenario file is JSON under ``load-tests/scenarios/``:

    {
      "schema": "load-scenario/v1",
      "name": "steady-state",
      "description": "...",
      "question_set": "load-tests/dataset/questions.json",
      "wait_min": 0.5,
      "wait_max": 2.0,
      "warmup": "15s",
      "stages": [
        {"duration": "120s", "users": 16, "spawn_rate": 4}
      ],
      "env": {"REDIS_URL": "redis://localhost:6379/0"},
      "pass_fail": {
        "max_error_rate": 0.01,
        "max_p95_ms": 2500,
        "min_throughput_rps": 5.0
      }
    }

``stages`` run top to bottom; a single-stage scenario holds load constant. The
first ``warmup`` seconds of the run are excluded from the scored aggregates by
``evaluation.performance.run``. ``env`` is applied to the stack the local runner
starts (for example, to point retrieval at a real Postgres and Redis for the
``cached`` scenario); it is ignored when running against an already-configured
Compose stack. ``pass_fail`` is checked against the scored window.

``schema`` is the record-format version and is checked on load. ``name`` must
match the file stem so a scenario can be named on the command line.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "load-scenario/v1"

# Every profile the performance plan calls for. ``load_all_scenarios`` fails if
# the committed directory does not define all of them.
REQUIRED_SCENARIOS = ("smoke", "steady-state", "ramp", "burst", "cached", "uncached")

_DEFAULT_QUESTION_SET = "load-tests/dataset/questions.json"

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_DURATION_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h)$")
_DURATION_UNIT_SECONDS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}

_SCENARIO_FIELDS = {
    "schema",
    "name",
    "description",
    "question_set",
    "wait_min",
    "wait_max",
    "warmup",
    "stages",
    "env",
    "pass_fail",
}
_STAGE_FIELDS = {"duration", "users", "spawn_rate"}
_PASS_FAIL_FIELDS = {"max_error_rate", "max_p95_ms", "min_throughput_rps"}


class ScenarioError(ValueError):
    """A scenario file is missing, malformed, or fails a schema rule."""


@dataclass(frozen=True)
class LoadStage:
    """One phase of a run: hold ``users`` for ``duration_seconds``."""

    duration_seconds: float
    users: int
    spawn_rate: float


@dataclass(frozen=True)
class PassFail:
    """Thresholds checked against the scored (post-warm-up) window."""

    max_error_rate: float
    max_p95_ms: float
    min_throughput_rps: float | None = None


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    question_set: str
    wait_min: float
    wait_max: float
    warmup_seconds: float
    stages: tuple[LoadStage, ...]
    pass_fail: PassFail
    env: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = field(default=None, compare=False)

    @property
    def run_time_seconds(self) -> float:
        return sum(stage.duration_seconds for stage in self.stages)

    @property
    def peak_users(self) -> int:
        return max(stage.users for stage in self.stages)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScenarioError(message)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _parse_duration(value: object, *, field_name: str, allow_zero: bool = False) -> float:
    _require(isinstance(value, str), f"{field_name} must be a string like '90s' or '2m'")
    assert isinstance(value, str)
    match = _DURATION_RE.match(value.strip())
    _require(
        match is not None,
        f"{field_name} {value!r} is not a duration like '500ms', '90s', '2m', '1h'",
    )
    assert match is not None
    seconds = float(match.group("value")) * _DURATION_UNIT_SECONDS[match.group("unit")]
    _require(
        seconds > 0 or (allow_zero and seconds == 0),
        f"{field_name} must be greater than zero",
    )
    return seconds


def _parse_positive_int(value: object, *, field_name: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool) and value >= 1,
        f"{field_name} must be an integer >= 1",
    )
    assert isinstance(value, int)
    return value


def _parse_positive_number(value: object, *, field_name: str) -> float:
    _require(_is_number(value) and value > 0, f"{field_name} must be a number > 0")
    assert isinstance(value, int | float)
    return float(value)


def _parse_stage(raw: object, *, index: int) -> LoadStage:
    _require(isinstance(raw, dict), f"stage {index}: must be a JSON object")
    assert isinstance(raw, dict)
    unknown = set(raw) - _STAGE_FIELDS
    _require(not unknown, f"stage {index}: unknown field(s): {', '.join(sorted(unknown))}")
    return LoadStage(
        duration_seconds=_parse_duration(raw.get("duration"), field_name=f"stage {index} duration"),
        users=_parse_positive_int(raw.get("users"), field_name=f"stage {index} users"),
        spawn_rate=_parse_positive_number(
            raw.get("spawn_rate"), field_name=f"stage {index} spawn_rate"
        ),
    )


def _parse_pass_fail(raw: object) -> PassFail:
    _require(isinstance(raw, dict), "pass_fail must be a JSON object")
    assert isinstance(raw, dict)
    unknown = set(raw) - _PASS_FAIL_FIELDS
    _require(not unknown, f"pass_fail: unknown field(s): {', '.join(sorted(unknown))}")

    error_rate = raw.get("max_error_rate")
    _require(
        _is_number(error_rate) and 0 <= error_rate <= 1,
        "pass_fail.max_error_rate must be a number in [0, 1]",
    )
    p95 = raw.get("max_p95_ms")
    _require(_is_number(p95) and p95 > 0, "pass_fail.max_p95_ms must be a number > 0")

    throughput = raw.get("min_throughput_rps")
    if throughput is not None:
        _require(
            _is_number(throughput) and throughput > 0,
            "pass_fail.min_throughput_rps must be a number > 0 when set",
        )
    assert isinstance(error_rate, int | float)
    assert isinstance(p95, int | float)
    return PassFail(
        max_error_rate=float(error_rate),
        max_p95_ms=float(p95),
        min_throughput_rps=float(throughput) if throughput is not None else None,
    )


def parse_scenario(payload: object, *, source_path: Path | None = None) -> Scenario:
    """Validate an already-decoded scenario object and return it typed."""
    _require(isinstance(payload, dict), "scenario root must be a JSON object")
    assert isinstance(payload, dict)

    unknown = set(payload) - _SCENARIO_FIELDS
    _require(not unknown, f"unknown field(s): {', '.join(sorted(unknown))}")

    _require(
        payload.get("schema") == SCHEMA_VERSION,
        f"unsupported scenario schema {payload.get('schema')!r}; expected {SCHEMA_VERSION!r}",
    )

    name = payload.get("name")
    _require(
        isinstance(name, str) and _NAME_RE.match(name) is not None,
        "name must be a lowercase slug (letters, digits, hyphen)",
    )
    assert isinstance(name, str)

    description = payload.get("description", "")
    _require(
        isinstance(description, str) and description.strip() != "",
        "description must be a non-empty string",
    )
    assert isinstance(description, str)

    question_set = payload.get("question_set", _DEFAULT_QUESTION_SET)
    _require(
        isinstance(question_set, str) and question_set.strip() != "",
        "question_set must be a non-empty string path",
    )
    assert isinstance(question_set, str)

    wait_min = payload.get("wait_min", 0.5)
    wait_max = payload.get("wait_max", 2.0)
    _require(
        _is_number(wait_min) and _is_number(wait_max) and 0 <= wait_min <= wait_max,
        "wait_min/wait_max must satisfy 0 <= wait_min <= wait_max",
    )
    assert isinstance(wait_min, int | float)
    assert isinstance(wait_max, int | float)

    warmup_seconds = _parse_duration(
        payload.get("warmup", "0s"), field_name="warmup", allow_zero=True
    )

    raw_stages = payload.get("stages")
    _require(
        isinstance(raw_stages, list) and len(raw_stages) >= 1,
        "stages must be a non-empty list",
    )
    assert isinstance(raw_stages, list)
    stages = tuple(_parse_stage(raw, index=i) for i, raw in enumerate(raw_stages))

    raw_env = payload.get("env", {})
    _require(
        isinstance(raw_env, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in raw_env.items()),
        "env must be an object mapping string keys to string values",
    )
    assert isinstance(raw_env, dict)

    _require("pass_fail" in payload, "scenario needs a pass_fail object")
    pass_fail = _parse_pass_fail(payload["pass_fail"])

    scenario = Scenario(
        name=name,
        description=description,
        question_set=question_set,
        wait_min=float(wait_min),
        wait_max=float(wait_max),
        warmup_seconds=warmup_seconds,
        stages=stages,
        pass_fail=pass_fail,
        env=dict(raw_env),
        source_path=source_path,
    )
    _require(
        scenario.warmup_seconds < scenario.run_time_seconds,
        "warmup must be shorter than the total run time",
    )
    return scenario


def load_scenario(path: str | Path) -> Scenario:
    """Read and validate a scenario file; its name must match the file stem."""
    scenario_path = Path(path)
    try:
        raw_text = scenario_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ScenarioError(f"cannot read scenario {scenario_path}: {error}") from error
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ScenarioError(f"scenario {scenario_path} is not valid JSON: {error}") from error
    scenario = parse_scenario(payload, source_path=scenario_path)
    _require(
        scenario.name == scenario_path.stem,
        f"scenario name {scenario.name!r} does not match file name {scenario_path.stem!r}",
    )
    return scenario


DEFAULT_SCENARIO_DIR = Path(__file__).resolve().parents[2] / "load-tests" / "scenarios"


def load_all_scenarios(directory: str | Path | None = None) -> dict[str, Scenario]:
    """Load every ``*.json`` scenario in a directory, keyed by name.

    Fails if any profile in ``REQUIRED_SCENARIOS`` is absent.
    """
    scenario_dir = Path(directory) if directory is not None else DEFAULT_SCENARIO_DIR
    _require(scenario_dir.is_dir(), f"scenario directory {scenario_dir} does not exist")
    scenarios: dict[str, Scenario] = {}
    for scenario_path in sorted(scenario_dir.glob("*.json")):
        scenario = load_scenario(scenario_path)
        scenarios[scenario.name] = scenario
    missing = [name for name in REQUIRED_SCENARIOS if name not in scenarios]
    _require(not missing, f"scenario directory is missing: {', '.join(missing)}")
    return scenarios
