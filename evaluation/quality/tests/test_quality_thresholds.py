from pathlib import Path

import pytest

from evaluation.quality.thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    ThresholdError,
    Thresholds,
    check_thresholds,
    load_thresholds,
    parse_thresholds,
)

PASSING_METRICS = {
    "retrieval_recall": 1.0,
    "retrieval_mrr": 1.0,
    "retrieval_precision_at_1": 1.0,
    "citation_presence": 1.0,
    "citation_accuracy": 0.93,
    "answer_correctness": 1.0,
    "answer_score": 1.0,
    "hallucination_rate": 0.0,
}


def test_committed_thresholds_file_parses() -> None:
    thresholds = load_thresholds()
    assert DEFAULT_THRESHOLDS_PATH.exists()
    assert thresholds.minimums["answer_correctness"] == 1.0
    assert thresholds.maximums["hallucination_rate"] == 0.0


def test_baseline_metrics_pass_the_committed_gate() -> None:
    regressions = check_thresholds(PASSING_METRICS, load_thresholds())
    assert regressions == []


def test_check_thresholds_flags_a_floor_breach() -> None:
    thresholds = Thresholds(minimums={"answer_correctness": 1.0}, maximums={})
    regressions = check_thresholds({"answer_correctness": 0.8}, thresholds)
    assert len(regressions) == 1
    assert regressions[0].metric == "answer_correctness"
    assert regressions[0].direction == "floor"
    assert regressions[0].as_dict() == {
        "metric": "answer_correctness",
        "value": 0.8,
        "threshold": 1.0,
        "direction": "floor",
    }


def test_check_thresholds_flags_a_ceiling_breach() -> None:
    thresholds = Thresholds(minimums={}, maximums={"hallucination_rate": 0.0})
    regressions = check_thresholds({"hallucination_rate": 0.1}, thresholds)
    assert regressions[0].direction == "ceiling"


def test_check_thresholds_ignores_absent_metrics() -> None:
    thresholds = Thresholds(minimums={"retrieval_recall": 1.0}, maximums={})
    assert check_thresholds({"answer_correctness": 1.0}, thresholds) == []


def test_parse_thresholds_rejects_unknown_metric() -> None:
    with pytest.raises(ThresholdError, match="unknown metric"):
        parse_thresholds({"min": {"made_up": 0.5}})


def test_parse_thresholds_rejects_out_of_range_value() -> None:
    with pytest.raises(ThresholdError, match="between 0 and 1"):
        parse_thresholds({"min": {"retrieval_recall": 1.5}})


def test_parse_thresholds_rejects_empty_bounds() -> None:
    with pytest.raises(ThresholdError, match="sets no bounds"):
        parse_thresholds({"min": {}, "max": {}})


def test_load_thresholds_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ThresholdError, match="cannot read thresholds"):
        load_thresholds(tmp_path / "nope.json")


def test_load_thresholds_reports_bad_json(tmp_path: Path) -> None:
    bad = tmp_path / "t.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(ThresholdError, match="not valid JSON"):
        load_thresholds(bad)
