"""The CI quality gate.

This test runs the full offline evaluation on the committed dataset and fails
when any metric breaches the committed thresholds. It uses only the
deterministic retrieval corpus and the deterministic inference backend, so it
needs no GPU, model download, or running service, and it runs as part of the
normal ``pytest`` suite.
"""

from pathlib import Path

from evaluation.quality.harness import run_evaluation
from evaluation.quality.schema import load_dataset
from evaluation.quality.thresholds import check_thresholds, load_thresholds

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "quality-core-v1.json"


def test_quality_metrics_meet_committed_thresholds() -> None:
    run = run_evaluation(load_dataset(DATASET_PATH))
    regressions = check_thresholds(run.metrics.as_dict(), load_thresholds())
    assert regressions == [], (
        "quality regression against evaluation/quality/thresholds.json: "
        + "; ".join(
            f"{item.metric}={item.value:.3f} vs "
            f"{'<=' if item.direction == 'ceiling' else '>='} {item.threshold:.3f}"
            for item in regressions
        )
    )
