from evaluation.quality.judge import KeywordJudge
from evaluation.quality.metrics import (
    aggregate_metrics,
    detect_hallucination,
    evaluate_case,
    score_citations,
    score_retrieval,
)
from evaluation.quality.schema import EvaluationCase


def make_case(**overrides) -> EvaluationCase:
    base = dict(
        id="c1",
        question="q",
        kind="retrieval",
        reference_answer="ref",
        expected_evidence=("doc-a",),
        answer_must_include=("keyword",),
        answer_must_not_include=(),
    )
    base.update(overrides)
    return EvaluationCase(**base)


# --- score_retrieval -------------------------------------------------------


def test_score_retrieval_perfect_rank() -> None:
    recall, rr, p1 = score_retrieval(make_case(), ("doc-a", "doc-b"))
    assert (recall, rr, p1) == (1.0, 1.0, 1.0)


def test_score_retrieval_second_place_hit() -> None:
    recall, rr, p1 = score_retrieval(make_case(), ("doc-b", "doc-a"))
    assert recall == 1.0
    assert rr == 0.5
    assert p1 == 0.0


def test_score_retrieval_miss() -> None:
    recall, rr, p1 = score_retrieval(make_case(), ("doc-b", "doc-c"))
    assert (recall, rr, p1) == (0.0, 0.0, 0.0)


def test_score_retrieval_partial_recall_two_expected() -> None:
    case = make_case(expected_evidence=("doc-a", "doc-d"))
    recall, rr, p1 = score_retrieval(case, ("doc-a", "doc-b"))
    assert recall == 0.5
    assert rr == 1.0


def test_score_retrieval_is_none_for_non_retrieving_kinds() -> None:
    assert score_retrieval(make_case(kind="direct", expected_evidence=()), ()) == (
        None,
        None,
        None,
    )


# --- score_citations -----------------------------------------------------


def test_citation_present_requires_marker_and_attached_citation() -> None:
    present, accuracy = score_citations(make_case(), "answer [1]", ("doc-a",))
    assert present is True
    assert accuracy == 1.0


def test_citation_absent_when_no_marker() -> None:
    present, accuracy = score_citations(make_case(), "answer with no marker", ("doc-a",))
    assert present is False


def test_citation_accuracy_penalises_off_target_citation() -> None:
    present, accuracy = score_citations(make_case(), "answer [1][2]", ("doc-a", "doc-x"))
    assert accuracy == 0.5


def test_citation_scope_none_for_insufficient_but_accuracy_rewards_silence() -> None:
    present, accuracy = score_citations(
        make_case(kind="insufficient", expected_evidence=()), "no evidence", ()
    )
    assert present is None
    assert accuracy == 1.0


def test_citation_accuracy_zero_when_insufficient_case_cites() -> None:
    _, accuracy = score_citations(
        make_case(kind="insufficient", expected_evidence=()), "text [1]", ("doc-a",)
    )
    assert accuracy == 0.0


# --- detect_hallucination ----------------------------------------------------


def test_hallucination_on_fabricated_citation() -> None:
    flagged, reason = detect_hallucination(
        make_case(), "answer [1]", ("doc-ghost",), ("doc-a",)
    )
    assert flagged is True
    assert "doc-ghost" in reason


def test_hallucination_on_marker_without_citation() -> None:
    flagged, _ = detect_hallucination(make_case(), "answer [1]", (), ("doc-a",))
    assert flagged is True


def test_insufficient_answer_that_does_not_decline_is_hallucination() -> None:
    flagged, _ = detect_hallucination(
        make_case(kind="insufficient", expected_evidence=()),
        "The capital is Paris.",
        (),
        (),
    )
    assert flagged is True


def test_insufficient_answer_that_declines_is_clean() -> None:
    flagged, _ = detect_hallucination(
        make_case(kind="insufficient", expected_evidence=()),
        "The retrieved evidence does not support an answer to this question.",
        (),
        (),
    )
    assert flagged is False


def test_direct_answer_with_citation_is_hallucination() -> None:
    flagged, _ = detect_hallucination(
        make_case(kind="direct", expected_evidence=()), "I can help [1]", ("doc-a",), ()
    )
    assert flagged is True


def test_grounded_retrieval_answer_is_clean() -> None:
    flagged, reason = detect_hallucination(
        make_case(), "Based on the evidence, x. [1]", ("doc-a",), ("doc-a", "doc-b")
    )
    assert flagged is False
    assert reason == ""


# --- evaluate_case + aggregate_metrics -------------------------------------


def _result(case, answer, ranked, retrieved, cited, trace=("Plan", "Retrieve", "Generate")):
    return evaluate_case(
        case,
        answer=answer,
        ranked_retrieval=ranked,
        workflow_retrieved=retrieved,
        cited=cited,
        trace=trace,
        judge=KeywordJudge(),
    )


def test_aggregate_metrics_over_a_mixed_run() -> None:
    results = [
        _result(
            make_case(id="r1"),
            "grounded keyword answer [1]",
            ("doc-a", "doc-b"),
            ("doc-a",),
            ("doc-a",),
        ),
        _result(
            make_case(id="w1", kind="rewrite"),
            "keyword answer [1]",
            ("doc-b", "doc-a"),
            ("doc-a",),
            ("doc-a",),
        ),
        _result(
            make_case(id="d1", kind="direct", expected_evidence=(), answer_must_include=()),
            "I answer questions about evaluations.",
            (),
            (),
            (),
            trace=("Plan", "Answer directly"),
        ),
        _result(
            make_case(
                id="i1",
                kind="insufficient",
                expected_evidence=(),
                answer_must_include=("does not support an answer",),
            ),
            "The retrieved evidence does not support an answer to this question.",
            (),
            (),
            (),
        ),
    ]
    metrics = aggregate_metrics(results)

    assert metrics.case_count == 4
    assert metrics.retrieval_recall == 1.0  # mean over r1 + w1 only
    assert metrics.retrieval_mrr == 0.75  # (1.0 + 0.5) / 2
    assert metrics.retrieval_precision_at_1 == 0.5
    assert metrics.citation_presence == 1.0  # r1 + w1
    assert metrics.answer_correctness == 1.0
    assert metrics.hallucination_rate == 0.0
    assert metrics.by_kind["retrieval"]["case_count"] == 1
    assert metrics.by_kind["direct"]["retrieval_recall"] == 1.0  # vacuous, no cases -> default
    assert set(metrics.as_dict()) == {
        "case_count",
        "retrieval_recall",
        "retrieval_mrr",
        "retrieval_precision_at_1",
        "citation_presence",
        "citation_accuracy",
        "answer_correctness",
        "answer_score",
        "hallucination_rate",
        "by_kind",
    }


def test_aggregate_metrics_flags_a_regressed_run() -> None:
    results = [
        _result(
            make_case(id="r1"),
            "an ungrounded answer missing the required term entirely",
            ("doc-x",),
            ("doc-x",),
            (),
        ),
    ]
    metrics = aggregate_metrics(results)
    assert metrics.retrieval_recall == 0.0
    assert metrics.answer_correctness == 0.0
    assert metrics.citation_presence == 0.0
    assert metrics.hallucination_rate == 1.0  # substantive claim, no citation
