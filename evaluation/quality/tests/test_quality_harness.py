from pathlib import Path

import pytest
from agent_service.workflow import WorkflowConfig

from evaluation.quality.harness import run_evaluation
from evaluation.quality.judge import KeywordJudge, ModelJudge
from evaluation.quality.schema import load_dataset

DATASET_PATH = Path(__file__).resolve().parents[2] / "datasets" / "quality-core-v1.json"


@pytest.fixture(scope="module")
def dataset():
    return load_dataset(DATASET_PATH)


@pytest.fixture(scope="module")
def run(dataset):
    return run_evaluation(dataset)


def test_run_scores_every_case(run, dataset) -> None:
    assert run.metrics.case_count == len(dataset.cases)
    assert {r.case_id for r in run.results} == {c.id for c in dataset.cases}
    assert run.results[0].case_id == dataset.cases[0].id  # order preserved


def test_committed_dataset_is_fully_answered_by_the_deterministic_stack(run) -> None:
    # The dataset is authored so the offline stack answers it cleanly; this is
    # the baseline the CI thresholds are set just beneath.
    assert run.metrics.answer_correctness == 1.0
    assert run.metrics.retrieval_recall == 1.0
    assert run.metrics.retrieval_precision_at_1 == 1.0
    assert run.metrics.citation_presence == 1.0
    assert run.metrics.hallucination_rate == 0.0
    assert run.metrics.citation_accuracy >= 0.85


def test_direct_cases_never_retrieve_or_cite(run) -> None:
    for result in run.results:
        if result.kind == "direct":
            assert result.trace == ("Plan", "Answer directly")
            assert result.cited == ()
            assert result.retrieval_recall is None


def test_rewrite_cases_exercise_the_rewrite_path(run) -> None:
    rewrites = [r for r in run.results if r.kind == "rewrite"]
    assert rewrites
    for result in rewrites:
        assert "Rewrite query" in result.trace
        assert result.retrieval_recall == 1.0
        assert result.cited  # recovered evidence is cited


def test_insufficient_cases_decline_without_citations(run) -> None:
    for result in run.results:
        if result.kind == "insufficient":
            assert result.cited == ()
            assert "does not support an answer" in result.answer.casefold()
            assert result.hallucinated is False


def test_run_is_deterministic(dataset) -> None:
    first = run_evaluation(dataset)
    second = run_evaluation(dataset)
    assert first.metrics.as_dict() == second.metrics.as_dict()
    assert [r.answer for r in first.results] == [r.answer for r in second.results]


def test_run_records_configuration(run) -> None:
    assert run.retrieval_mode == "in-memory-keyword"
    assert run.inference_backend == "deterministic"
    assert run.inference_model == "deterministic-grounded-v1"
    assert run.judge_name == "keyword"
    assert run.top_k == 3
    assert run.corpus_size == 4
    assert isinstance(run.workflow_config, WorkflowConfig)


def test_tighter_relevance_floor_changes_the_outcome(dataset) -> None:
    strict = run_evaluation(
        dataset, workflow_config=WorkflowConfig(min_relevance=0.99, min_results=1)
    )
    # Nothing clears a 0.99 similarity bar, so the retrieving cases lose their
    # citations and correctness falls.
    assert strict.metrics.answer_correctness < 1.0


def test_run_accepts_an_injected_judge(dataset) -> None:
    always_fail = ModelJudge(client=lambda _prompt: "SCORE: 0.0\nVERDICT: fail")
    run = run_evaluation(dataset, judge=always_fail)
    assert run.metrics.answer_correctness == 0.0
    assert run.judge_name == "model"


def test_keyword_judge_is_the_default(dataset) -> None:
    run = run_evaluation(dataset, judge=KeywordJudge())
    assert run.judge_name == "keyword"
