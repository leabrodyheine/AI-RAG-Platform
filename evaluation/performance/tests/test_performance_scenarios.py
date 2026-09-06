import json
from pathlib import Path

import pytest

from evaluation.performance.scenarios import (
    REQUIRED_SCENARIOS,
    SCHEMA_VERSION,
    Scenario,
    ScenarioError,
    load_all_scenarios,
    load_scenario,
    parse_scenario,
)

SCENARIO_DIR = Path(__file__).resolve().parents[2] / "load-tests" / "scenarios"


def _valid_payload() -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "name": "unit",
        "description": "A scenario used only by the unit tests.",
        "warmup": "5s",
        "stages": [
            {"duration": "30s", "users": 8, "spawn_rate": 4},
            {"duration": "30s", "users": 16, "spawn_rate": 4},
        ],
        "pass_fail": {
            "max_error_rate": 0.01,
            "max_p95_ms": 2500,
            "min_throughput_rps": 5.0,
        },
    }


def test_committed_directory_defines_every_required_scenario() -> None:
    scenarios = load_all_scenarios()
    assert set(scenarios) == set(REQUIRED_SCENARIOS)
    for scenario in scenarios.values():
        assert isinstance(scenario, Scenario)
        assert scenario.description.strip()
        assert scenario.stages
        assert scenario.warmup_seconds < scenario.run_time_seconds


def test_every_committed_scenario_name_matches_its_file_stem() -> None:
    for scenario_path in SCENARIO_DIR.glob("*.json"):
        scenario = load_scenario(scenario_path)
        assert scenario.name == scenario_path.stem


def test_committed_scenarios_are_pretty_printed_json() -> None:
    for scenario_path in SCENARIO_DIR.glob("*.json"):
        text = scenario_path.read_text(encoding="utf-8")
        assert text.startswith("{\n"), scenario_path.name
        json.loads(text)


def test_ramp_steps_users_upward_and_burst_spikes() -> None:
    scenarios = load_all_scenarios()

    ramp_users = [stage.users for stage in scenarios["ramp"].stages]
    assert ramp_users == sorted(ramp_users)
    assert len(set(ramp_users)) > 1

    burst = scenarios["burst"]
    assert burst.peak_users >= 4 * burst.stages[0].users
    assert burst.stages[-1].users == burst.stages[0].users  # returns to calm


def test_cached_scenario_points_retrieval_at_a_backing_store() -> None:
    cached = load_all_scenarios()["cached"]
    assert "REDIS_URL" in cached.env
    assert load_all_scenarios()["uncached"].env == {}


def test_parse_scenario_round_trips_and_computes_totals() -> None:
    scenario = parse_scenario(_valid_payload())
    assert scenario.name == "unit"
    assert scenario.run_time_seconds == pytest.approx(60.0)
    assert scenario.peak_users == 16
    assert scenario.warmup_seconds == pytest.approx(5.0)
    assert scenario.pass_fail.min_throughput_rps == pytest.approx(5.0)


def test_min_throughput_is_optional() -> None:
    payload = _valid_payload()
    del payload["pass_fail"]["min_throughput_rps"]
    assert parse_scenario(payload).pass_fail.min_throughput_rps is None


def test_unknown_schema_version_is_rejected() -> None:
    payload = _valid_payload()
    payload["schema"] = "load-scenario/v99"
    with pytest.raises(ScenarioError, match="unsupported scenario schema"):
        parse_scenario(payload)


def test_unknown_top_level_field_is_rejected() -> None:
    payload = _valid_payload()
    payload["warm_up"] = "5s"
    with pytest.raises(ScenarioError, match="unknown field"):
        parse_scenario(payload)


def test_unknown_stage_field_is_rejected() -> None:
    payload = _valid_payload()
    payload["stages"][0]["duratoin"] = "30s"
    with pytest.raises(ScenarioError, match="stage 0: unknown field"):
        parse_scenario(payload)


def test_malformed_duration_is_rejected() -> None:
    payload = _valid_payload()
    payload["stages"][0]["duration"] = "30 seconds"
    with pytest.raises(ScenarioError, match="is not a duration"):
        parse_scenario(payload)


def test_zero_user_stage_is_rejected() -> None:
    payload = _valid_payload()
    payload["stages"][0]["users"] = 0
    with pytest.raises(ScenarioError, match="users must be an integer >= 1"):
        parse_scenario(payload)


def test_boolean_is_not_accepted_as_a_number() -> None:
    payload = _valid_payload()
    payload["stages"][0]["spawn_rate"] = True
    with pytest.raises(ScenarioError, match="spawn_rate must be a number > 0"):
        parse_scenario(payload)


def test_empty_stage_list_is_rejected() -> None:
    payload = _valid_payload()
    payload["stages"] = []
    with pytest.raises(ScenarioError, match="stages must be a non-empty list"):
        parse_scenario(payload)


def test_warmup_not_shorter_than_run_time_is_rejected() -> None:
    payload = _valid_payload()
    payload["warmup"] = "60s"
    with pytest.raises(ScenarioError, match="warmup must be shorter"):
        parse_scenario(payload)


def test_error_rate_outside_unit_interval_is_rejected() -> None:
    payload = _valid_payload()
    payload["pass_fail"]["max_error_rate"] = 1.5
    with pytest.raises(ScenarioError, match=r"max_error_rate must be a number in \[0, 1\]"):
        parse_scenario(payload)


def test_non_positive_p95_threshold_is_rejected() -> None:
    payload = _valid_payload()
    payload["pass_fail"]["max_p95_ms"] = 0
    with pytest.raises(ScenarioError, match="max_p95_ms must be a number > 0"):
        parse_scenario(payload)


def test_wait_bounds_must_be_ordered() -> None:
    payload = _valid_payload()
    payload["wait_min"] = 3.0
    payload["wait_max"] = 1.0
    with pytest.raises(ScenarioError, match="wait_min/wait_max"):
        parse_scenario(payload)


def test_env_must_be_string_to_string() -> None:
    payload = _valid_payload()
    payload["env"] = {"REDIS_URL": 6379}
    with pytest.raises(ScenarioError, match="env must be an object"):
        parse_scenario(payload)


def test_load_scenario_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="cannot read scenario"):
        load_scenario(tmp_path / "missing.json")


def test_load_scenario_reports_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ScenarioError, match="not valid JSON"):
        load_scenario(bad)


def test_load_scenario_rejects_name_file_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    path = tmp_path / "elsewhere.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ScenarioError, match="does not match file name"):
        load_scenario(path)


def test_load_all_scenarios_requires_the_full_set(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["name"] = "smoke"
    (tmp_path / "smoke.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(ScenarioError, match="missing: steady-state"):
        load_all_scenarios(tmp_path)
