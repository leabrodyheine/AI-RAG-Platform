"""Scoring for one replayed dataset.

Nothing here imports a service. The harness runs the workflow, hands each case
its retrieved document ids, cited ids, answer text, and trace, and these
functions turn that into per-case scores and dataset-level metrics:

* retrieval recall, mean reciprocal rank, precision@1 (retrieval + rewrite cases)
* citation presence and citation-source accuracy
* answer correctness (delegated to an :mod:`evaluation.quality.judge`)
* hallucination / unsupported-claim rate
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import fmean

from evaluation.quality.judge import AnswerJudge
from evaluation.quality.schema import CASE_KINDS, EvaluationCase

_CITATION_MARKER = re.compile(r"\[\d+\]")
# A stable fragment of the deterministic backend's insufficient-evidence reply.
_DECLINED_FRAGMENT = "does not support an answer"
_RETRIEVING_KINDS = ("retrieval", "rewrite")


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    kind: str
    question: str
    answer: str
    ranked_retrieval: tuple[str, ...]
    workflow_retrieved: tuple[str, ...]
    cited: tuple[str, ...]
    trace: tuple[str, ...]
    retrieval_recall: float | None
    reciprocal_rank: float | None
    precision_at_1: float | None
    citation_present: bool | None
    citation_accuracy: float
    answer_passed: bool
    answer_score: float
    answer_rationale: str
    hallucinated: bool
    hallucination_reason: str


def score_retrieval(
    case: EvaluationCase,
    ranked_retrieval: tuple[str, ...],
) -> tuple[float | None, float | None, float | None]:
    """Recall, reciprocal rank, and precision@1 for a retrieving case."""
    if case.kind not in _RETRIEVING_KINDS:
        return None, None, None
    expected = set(case.expected_evidence)
    if not expected:
        return None, None, None

    retrieved = list(ranked_retrieval)
    recall = len(expected.intersection(retrieved)) / len(expected)

    first_hit_rank = next(
        (index + 1 for index, doc_id in enumerate(retrieved) if doc_id in expected),
        None,
    )
    reciprocal_rank = 1.0 / first_hit_rank if first_hit_rank is not None else 0.0
    precision_at_1 = 1.0 if retrieved and retrieved[0] in expected else 0.0
    return round(recall, 4), round(reciprocal_rank, 4), precision_at_1


def score_citations(
    case: EvaluationCase,
    answer: str,
    cited: tuple[str, ...],
) -> tuple[bool | None, float]:
    """Return (citation_present, citation_accuracy).

    ``citation_present`` is ``None`` for cases that are not expected to cite.
    ``citation_accuracy`` is defined for every case: for retrieving cases it is
    the share of cited ids that are expected evidence; for direct and
    insufficient cases it is 1.0 only when nothing was cited.
    """
    cited_set = set(cited)
    if case.kind in _RETRIEVING_KINDS:
        present = bool(cited_set) and bool(_CITATION_MARKER.search(answer))
        expected = set(case.expected_evidence)
        accuracy = len(cited_set.intersection(expected)) / len(cited_set) if cited_set else 0.0
        return present, round(accuracy, 4)
    return None, (1.0 if not cited_set else 0.0)


def detect_hallucination(
    case: EvaluationCase,
    answer: str,
    cited: tuple[str, ...],
    workflow_retrieved: tuple[str, ...],
) -> tuple[bool, str]:
    """Flag answers that assert more than the retrieved evidence supports."""
    cited_set = set(cited)
    retrieved_set = set(workflow_retrieved)
    has_marker = bool(_CITATION_MARKER.search(answer))
    declined = _DECLINED_FRAGMENT in answer.casefold()

    fabricated = sorted(cited_set - retrieved_set)
    if fabricated:
        return True, f"cited {fabricated} which retrieval never returned"
    if has_marker and not cited_set:
        return True, "answer carries a [n] marker but no citation was attached"
    if cited_set and not has_marker:
        return True, "citations attached but the answer references none of them"

    if case.kind == "direct":
        if cited_set or has_marker:
            return True, "a direct answer must not cite sources"
        return False, ""
    if case.kind == "insufficient":
        if not declined:
            return True, "no supporting evidence exists but the answer did not decline"
        if cited_set:
            return True, "declined the question yet still attached citations"
        return False, ""
    # retrieval / rewrite
    if not declined and not cited_set:
        return True, "made a substantive claim with no citation"
    return False, ""


def evaluate_case(
    case: EvaluationCase,
    *,
    answer: str,
    ranked_retrieval: tuple[str, ...],
    workflow_retrieved: tuple[str, ...],
    cited: tuple[str, ...],
    trace: tuple[str, ...],
    judge: AnswerJudge,
) -> CaseResult:
    recall, reciprocal_rank, precision_at_1 = score_retrieval(case, ranked_retrieval)
    present, accuracy = score_citations(case, answer, cited)
    verdict = judge.score(case, answer)
    hallucinated, reason = detect_hallucination(case, answer, cited, workflow_retrieved)
    return CaseResult(
        case_id=case.id,
        kind=case.kind,
        question=case.question,
        answer=answer,
        ranked_retrieval=tuple(ranked_retrieval),
        workflow_retrieved=tuple(workflow_retrieved),
        cited=tuple(cited),
        trace=tuple(trace),
        retrieval_recall=recall,
        reciprocal_rank=reciprocal_rank,
        precision_at_1=precision_at_1,
        citation_present=present,
        citation_accuracy=accuracy,
        answer_passed=verdict.passed,
        answer_score=verdict.score,
        answer_rationale=verdict.rationale,
        hallucinated=hallucinated,
        hallucination_reason=reason,
    )


@dataclass(frozen=True)
class QualityMetrics:
    case_count: int
    retrieval_recall: float
    retrieval_mrr: float
    retrieval_precision_at_1: float
    citation_presence: float
    citation_accuracy: float
    answer_correctness: float
    answer_score: float
    hallucination_rate: float
    by_kind: dict[str, dict[str, float | int]]

    def as_dict(self) -> dict[str, object]:
        return {
            "case_count": self.case_count,
            "retrieval_recall": self.retrieval_recall,
            "retrieval_mrr": self.retrieval_mrr,
            "retrieval_precision_at_1": self.retrieval_precision_at_1,
            "citation_presence": self.citation_presence,
            "citation_accuracy": self.citation_accuracy,
            "answer_correctness": self.answer_correctness,
            "answer_score": self.answer_score,
            "hallucination_rate": self.hallucination_rate,
            "by_kind": self.by_kind,
        }


def _mean(values: list[float], *, default: float = 1.0) -> float:
    return round(fmean(values), 4) if values else default


def aggregate_metrics(results: list[CaseResult]) -> QualityMetrics:
    if not results:
        raise ValueError("cannot aggregate an empty result set")

    retrieval_scoped = [r for r in results if r.retrieval_recall is not None]
    citation_scoped = [r for r in results if r.citation_present is not None]

    by_kind: dict[str, dict[str, float | int]] = {}
    for kind in CASE_KINDS:
        bucket = [r for r in results if r.kind == kind]
        if not bucket:
            continue
        kind_retrieval = [r for r in bucket if r.retrieval_recall is not None]
        kind_citation = [r for r in bucket if r.citation_present is not None]
        by_kind[kind] = {
            "case_count": len(bucket),
            "answer_correctness": _mean([1.0 if r.answer_passed else 0.0 for r in bucket]),
            "hallucination_rate": _mean(
                [1.0 if r.hallucinated else 0.0 for r in bucket], default=0.0
            ),
            "retrieval_recall": _mean([r.retrieval_recall for r in kind_retrieval]),  # type: ignore[misc]
            "citation_presence": _mean(
                [1.0 if r.citation_present else 0.0 for r in kind_citation]
            ),
        }

    return QualityMetrics(
        case_count=len(results),
        retrieval_recall=_mean([r.retrieval_recall for r in retrieval_scoped]),  # type: ignore[misc]
        retrieval_mrr=_mean([r.reciprocal_rank for r in retrieval_scoped]),  # type: ignore[misc]
        retrieval_precision_at_1=_mean(
            [r.precision_at_1 for r in retrieval_scoped]  # type: ignore[misc]
        ),
        citation_presence=_mean([1.0 if r.citation_present else 0.0 for r in citation_scoped]),
        citation_accuracy=_mean([r.citation_accuracy for r in results]),
        answer_correctness=_mean([1.0 if r.answer_passed else 0.0 for r in results]),
        answer_score=_mean([r.answer_score for r in results]),
        hallucination_rate=_mean(
            [1.0 if r.hallucinated else 0.0 for r in results], default=0.0
        ),
        by_kind=by_kind,
    )
