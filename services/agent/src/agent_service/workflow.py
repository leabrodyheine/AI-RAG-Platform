"""A small, bounded, observable RAG workflow.

This is a fixed decision loop, not an open-ended agent: decide whether retrieval
is needed, retrieve, assess the evidence, optionally rewrite the query once and
retrieve again, then generate a grounded answer. Every decision, measurement,
and timing is recorded as a trace step; no hidden reasoning is exposed.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum

from agent_service.schemas import Citation


class WorkflowState(StrEnum):
    PLAN = "plan"
    RETRIEVE = "retrieve"
    ASSESS = "assess"
    REWRITE = "rewrite"
    GENERATE = "generate"
    DONE = "done"


@dataclass(frozen=True)
class WorkflowConfig:
    """Thresholds and the strict step ceiling for one workflow run."""

    min_relevance: float = 0.3
    min_results: int = 1
    # Maximum number of external calls (retrieval + generation) a run may make.
    # The loop is already structurally bounded to two retrievals and one
    # generation; this is the hard guard and is reported in the trace.
    max_steps: int = 4


DIRECT_ANSWER = (
    "I answer questions about this platform's AI evaluation results — retrieval "
    "quality, caching, inference performance, and answer accuracy. Ask about a "
    "specific run or metric and I'll cite the supporting evidence."
)

_GREETINGS = {
    "hi",
    "hey",
    "hello",
    "hey there",
    "hello there",
    "good morning",
    "good afternoon",
    "good evening",
}
_ASSISTANT_TOPICS = (
    "what can you do",
    "what do you do",
    "who are you",
    "what are you",
    "how do you work",
    "what can i ask",
    "what should i ask",
)
_STOP_TERMS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "did",
    "do",
    "does",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "me",
    "of",
    "on",
    "or",
    "please",
    "show",
    "so",
    "tell",
    "the",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "you",
    "your",
}
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievalDecision:
    retrieval_needed: bool
    detail: str
    direct_answer: str = ""


@dataclass(frozen=True)
class EvidenceAssessment:
    usable: list[Citation] = field(default_factory=list)
    strong: bool = False
    detail: str = ""


def keyword_string(text: str) -> str:
    """Lowercase content words of ``text`` joined by single spaces."""
    return " ".join(_WORD.findall(text.lower()))


def decide_retrieval(question: str) -> RetrievalDecision:
    """Decide deterministically whether the question needs evidence.

    There is no model router in this milestone; this heuristic is the fallback
    a router would defer to. Only a narrow, recognised set of questions skips
    retrieval.
    """
    normalized = " ".join(question.lower().split()).strip(" ?!.")
    if not _WORD.search(normalized):
        return RetrievalDecision(
            retrieval_needed=False,
            detail="no searchable terms in the question",
            direct_answer=DIRECT_ANSWER,
        )
    if normalized in _GREETINGS:
        return RetrievalDecision(
            retrieval_needed=False,
            detail="greeting; answering directly",
            direct_answer=DIRECT_ANSWER,
        )
    if any(topic in normalized for topic in _ASSISTANT_TOPICS):
        return RetrievalDecision(
            retrieval_needed=False,
            detail="question is about the assistant; answering directly",
            direct_answer=DIRECT_ANSWER,
        )
    return RetrievalDecision(
        retrieval_needed=True,
        detail="question needs evaluation evidence",
    )


def assess_evidence(
    citations: list[Citation],
    config: WorkflowConfig,
) -> EvidenceAssessment:
    """Grade retrieved evidence by result count and similarity threshold."""
    usable = [c for c in citations if c.relevance >= config.min_relevance]
    top = max((c.relevance for c in citations), default=0.0)
    strong = len(usable) >= config.min_results

    if not citations:
        detail = "no sources retrieved"
    elif strong:
        detail = (
            f"{len(usable)} of {len(citations)} sources at or above relevance "
            f"{config.min_relevance:g} (top {top:.2f})"
        )
    else:
        detail = (
            f"weak evidence: {len(usable)} of {len(citations)} sources usable, "
            f"top relevance {top:.2f} below {config.min_relevance:g}"
        )
    return EvidenceAssessment(usable=usable, strong=strong, detail=detail)


def is_better(candidate: EvidenceAssessment, incumbent: EvidenceAssessment) -> bool:
    """Whether ``candidate`` evidence should replace ``incumbent``."""
    if candidate.strong != incumbent.strong:
        return candidate.strong
    return len(candidate.usable) > len(incumbent.usable)


def rewrite_query(question: str) -> str:
    """Produce one deterministic keyword query, or ``""`` if nothing remains."""
    return " ".join(
        term for term in _WORD.findall(question.lower()) if term not in _STOP_TERMS
    )
