import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from evaluation.quality.harness import run_evaluation
from evaluation.quality.report import REPORT_SCHEMA, build_report, render_markdown, resolve_commit
from evaluation.quality.schema import load_dataset

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "quality-core-v1.json"


@pytest.fixture(scope="module")
def report() -> dict:
    run = run_evaluation(load_dataset(DATASET_PATH))
    return build_report(
        run,
        commit="abc1234",
        generated_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )


def test_report_run_block_captures_reproducibility_metadata(report: dict) -> None:
    run = report["run"]
    assert report["schema"] == REPORT_SCHEMA
    assert run["generated_at"] == "2026-01-02T03:04:05Z"
    assert run["commit"] == "abc1234"
    assert run["dataset"]["version"] == "core-v1"
    assert len(run["dataset"]["sha256"]) == 64
    assert run["dataset"]["embedding_version"] == "in-memory-keyword-v1"
    assert run["retrieval"] == {
        "mode": "in-memory-keyword",
        "corpus_size": 4,
        "top_k": 3,
    }
    assert run["inference"] == {"backend": "deterministic", "model": "deterministic-grounded-v1"}
    assert run["workflow"] == {"min_relevance": 0.3, "min_results": 1, "max_steps": 4}
    assert run["judge"] == "keyword"


def test_report_is_json_serialisable_and_has_a_case_per_record(report: dict) -> None:
    text = json.dumps(report, sort_keys=True)
    reloaded = json.loads(text)
    assert len(reloaded["cases"]) == report["metrics"]["case_count"]
    first = reloaded["cases"][0]
    assert {"case_id", "kind", "answer", "trace", "hallucinated"} <= set(first)


def test_render_markdown_without_thresholds(report: dict) -> None:
    md = render_markdown(report)
    assert md.startswith("# Quality evaluation report")
    assert "**Status:** PASS" in md
    assert "| Retrieval recall | 1.000 |" in md
    assert "## By case kind" in md
    assert "rewrite-cache-regression" in md
    assert "Threshold" not in md  # no threshold column when none provided


def test_render_markdown_with_thresholds_and_regression() -> None:
    run = run_evaluation(load_dataset(DATASET_PATH))
    thresholds = {"min": {"answer_correctness": 1.0}, "max": {"hallucination_rate": 0.0}}
    regressions = [
        {"metric": "answer_correctness", "value": 0.8, "threshold": 1.0, "direction": "floor"}
    ]
    report = build_report(run, thresholds=thresholds, regressions=regressions)
    md = render_markdown(report)
    assert "**Status:** FAIL" in md
    assert "| Answer correctness | 1.000 | ≥ 1.000 |" in md
    assert "| Hallucination rate | 0.000 | ≤ 0.000 | ok |" in md
    assert "## Regressions" in md
    assert "answer_correctness" in md.split("## Regressions", 1)[1]


def test_resolve_commit_returns_a_sha_or_unknown() -> None:
    commit = resolve_commit()
    assert commit == "unknown" or re.fullmatch(r"[0-9a-f]{40}", commit)
