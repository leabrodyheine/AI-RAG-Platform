import pytest
from agent_service.schemas import Citation
from agent_service.workflow import (
    DIRECT_ANSWER,
    WorkflowConfig,
    assess_evidence,
    decide_retrieval,
    is_better,
    keyword_string,
    rewrite_query,
)


def citation(relevance: float, ident: str = "c") -> Citation:
    return Citation(
        id=ident,
        title=f"Source {ident}",
        source=f"evaluation/{ident}.json",
        excerpt="Measured detail.",
        relevance=relevance,
    )


@pytest.mark.parametrize(
    "question",
    ["Hello", "  hi  ", "good morning", "What can you do?", "who are you", "?!"],
)
def test_decide_retrieval_answers_recognised_questions_directly(question: str) -> None:
    decision = decide_retrieval(question)

    assert decision.retrieval_needed is False
    assert decision.direct_answer == DIRECT_ANSWER
    assert decision.detail


@pytest.mark.parametrize(
    "question",
    [
        "Why did p95 latency regress in run 1842?",
        "Compare cached and uncached retrieval",
        "hello world throughput numbers",
    ],
)
def test_decide_retrieval_requires_evidence_for_real_questions(question: str) -> None:
    decision = decide_retrieval(question)

    assert decision.retrieval_needed is True
    assert decision.direct_answer == ""


def test_assess_evidence_flags_strong_evidence() -> None:
    config = WorkflowConfig(min_relevance=0.3, min_results=1)

    assessment = assess_evidence([citation(0.8, "a"), citation(0.1, "b")], config)

    assert assessment.strong is True
    assert [c.id for c in assessment.usable] == ["a"]
    assert "top 0.80" in assessment.detail


def test_assess_evidence_flags_weak_and_missing_evidence() -> None:
    config = WorkflowConfig(min_relevance=0.5, min_results=1)

    weak = assess_evidence([citation(0.2, "a"), citation(0.3, "b")], config)
    empty = assess_evidence([], config)

    assert weak.strong is False
    assert weak.usable == []
    assert "weak evidence" in weak.detail
    assert empty.strong is False
    assert empty.detail == "no sources retrieved"


def test_assess_evidence_respects_min_results() -> None:
    config = WorkflowConfig(min_relevance=0.3, min_results=2)

    one = assess_evidence([citation(0.9, "a")], config)
    two = assess_evidence([citation(0.9, "a"), citation(0.7, "b")], config)

    assert one.strong is False
    assert two.strong is True


def test_is_better_prefers_strong_then_more_usable() -> None:
    weak = assess_evidence([citation(0.1)], WorkflowConfig(min_relevance=0.3))
    strong_one = assess_evidence([citation(0.9, "a")], WorkflowConfig(min_relevance=0.3))
    strong_two = assess_evidence(
        [citation(0.9, "a"), citation(0.8, "b")], WorkflowConfig(min_relevance=0.3)
    )

    assert is_better(strong_one, weak) is True
    assert is_better(weak, strong_one) is False
    assert is_better(strong_two, strong_one) is True
    assert is_better(strong_one, strong_two) is False


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why did the p95 latency regress so badly?", "p95 latency regress badly"),
        ("What is the cache hit rate?", "cache hit rate"),
        ("why is it so", ""),
    ],
)
def test_rewrite_query_keeps_only_content_terms(question: str, expected: str) -> None:
    assert rewrite_query(question) == expected


def test_keyword_string_detects_an_unchanged_rewrite() -> None:
    question = "cache hit rate"

    assert rewrite_query(question) == keyword_string(question)
