import pytest

from evaluation.quality.judge import (
    JudgeError,
    KeywordJudge,
    ModelJudge,
    create_judge,
)
from evaluation.quality.schema import EvaluationCase


def case(**overrides) -> EvaluationCase:
    base = dict(
        id="c1",
        question="How much did p95 rise?",
        kind="retrieval",
        reference_answer="From 112 ms to 391 ms.",
        expected_evidence=("retrieval-benchmark-1842",),
        answer_must_include=("112 ms", "391 ms"),
        answer_must_not_include=(),
    )
    base.update(overrides)
    return EvaluationCase(**base)


def test_keyword_judge_passes_when_all_keys_present() -> None:
    verdict = KeywordJudge().score(case(), "It rose from 112 MS to 391 ms.")
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_keyword_judge_reports_missing_keys_and_partial_score() -> None:
    verdict = KeywordJudge().score(case(), "It rose to 391 ms.")
    assert verdict.passed is False
    assert verdict.score == 0.5
    assert "112 ms" in verdict.rationale


def test_keyword_judge_fails_and_zeroes_on_forbidden_text() -> None:
    verdict = KeywordJudge().score(
        case(answer_must_not_include=("Paris",)),
        "112 ms to 391 ms, near Paris",
    )
    assert verdict.passed is False
    assert verdict.score == 0.0
    assert "Paris" in verdict.rationale


def test_keyword_judge_passes_a_case_with_no_required_keys() -> None:
    verdict = KeywordJudge().score(
        case(kind="direct", expected_evidence=(), answer_must_include=()),
        "anything at all",
    )
    assert verdict.passed is True
    assert verdict.score == 1.0


def test_create_judge_returns_keyword_and_rejects_unknown() -> None:
    assert isinstance(create_judge("keyword"), KeywordJudge)
    with pytest.raises(ValueError, match="unknown judge"):
        create_judge("gpt-9")


def test_model_judge_parses_score_and_verdict() -> None:
    replies = ["SCORE: 0.9\nVERDICT: pass\nRATIONALE: consistent"]
    judge = ModelJudge(client=lambda _prompt: replies.pop(0))
    verdict = judge.score(case(), "112 ms to 391 ms")
    assert verdict.passed is True
    assert verdict.score == 0.9


def test_model_judge_falls_back_to_threshold_without_verdict_line() -> None:
    judge = ModelJudge(client=lambda _prompt: "SCORE: 0.4", pass_threshold=0.6)
    verdict = judge.score(case(), "weak answer")
    assert verdict.passed is False
    assert verdict.score == 0.4


def test_model_judge_clamps_out_of_range_scores() -> None:
    judge = ModelJudge(client=lambda _prompt: "SCORE: 1.7\nVERDICT: pass")
    assert judge.score(case(), "x").score == 1.0


def test_model_judge_raises_when_reply_has_no_score() -> None:
    judge = ModelJudge(client=lambda _prompt: "looks fine to me")
    with pytest.raises(JudgeError, match="no SCORE line"):
        judge.score(case(), "x")


def test_model_judge_wraps_client_failure() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("connection reset")

    with pytest.raises(JudgeError, match="connection reset"):
        ModelJudge(client=boom).score(case(), "x")


def test_model_judge_rejects_bad_threshold() -> None:
    with pytest.raises(ValueError, match="pass_threshold"):
        ModelJudge(client=lambda _p: "SCORE: 1", pass_threshold=2.0)


def test_model_judge_prompt_carries_question_reference_and_answer() -> None:
    seen: list[str] = []

    def client(prompt: str) -> str:
        seen.append(prompt)
        return "SCORE: 1\nVERDICT: pass"

    ModelJudge(client=client).score(case(), "candidate text here")
    assert "How much did p95 rise?" in seen[0]
    assert "From 112 ms to 391 ms." in seen[0]
    assert "candidate text here" in seen[0]
