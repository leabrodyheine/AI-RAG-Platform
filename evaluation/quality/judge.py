"""Answer-correctness judges.

Two implementations behind one Protocol:

* :class:`KeywordJudge` -- the deterministic baseline. An answer passes when
  every ``answer_must_include`` substring is present (case-insensitively) and
  no ``answer_must_not_include`` substring is. No model, no network, stable
  across runs; this is what the default report and CI use.
* :class:`ModelJudge` -- an optional LLM judge. It is a thin, tested seam: give
  it a ``client`` callable that takes a prompt and returns the model's reply,
  and it parses a ``SCORE`` / ``VERDICT`` verdict out of that reply. It is not
  wired into the default run because its output is not reproducible.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from evaluation.quality.schema import EvaluationCase


class JudgeError(RuntimeError):
    """A judge could not produce a verdict (e.g. unparseable model output)."""


@dataclass(frozen=True)
class JudgeVerdict:
    passed: bool
    score: float  # 0.0 .. 1.0
    rationale: str


class AnswerJudge(Protocol):
    name: str

    def score(self, case: EvaluationCase, answer: str) -> JudgeVerdict: ...


class KeywordJudge:
    """Deterministic substring judge driven by the case's answer keys."""

    name = "keyword"

    def score(self, case: EvaluationCase, answer: str) -> JudgeVerdict:
        haystack = answer.casefold()
        required = [key for key in case.answer_must_include]
        forbidden = [key for key in case.answer_must_not_include]

        hit = [key for key in required if key.casefold() in haystack]
        leaked = [key for key in forbidden if key.casefold() in haystack]

        # Coverage of the required keys, with any forbidden hit forcing 0.
        if leaked:
            score = 0.0
        elif not required:
            score = 1.0
        else:
            score = len(hit) / len(required)

        passed = not leaked and len(hit) == len(required)
        if passed:
            rationale = "all answer keys satisfied"
        elif leaked:
            rationale = f"answer contains forbidden text: {', '.join(leaked)}"
        else:
            missing = [key for key in required if key.casefold() not in haystack]
            rationale = f"missing required text: {', '.join(missing)}"
        return JudgeVerdict(passed=passed, score=round(score, 4), rationale=rationale)


_SCORE_PATTERN = re.compile(r"score\s*[:=]\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)
_VERDICT_PATTERN = re.compile(r"verdict\s*[:=]\s*(pass|fail|yes|no)", re.IGNORECASE)

MODEL_JUDGE_PROMPT = (
    "You are grading whether a candidate answer is factually consistent with a "
    "reference answer for the same question. Reply with two lines exactly:\n"
    "SCORE: <number from 0 to 1>\n"
    "VERDICT: <pass|fail>\n\n"
    "Question: {question}\n"
    "Reference answer: {reference}\n"
    "Candidate answer: {answer}\n"
)


class ModelJudge:
    """Optional LLM judge. ``client(prompt) -> reply`` supplies the model."""

    name = "model"

    def __init__(
        self,
        client: Callable[[str], str],
        *,
        pass_threshold: float = 0.6,
        prompt_template: str = MODEL_JUDGE_PROMPT,
    ) -> None:
        if not 0.0 <= pass_threshold <= 1.0:
            raise ValueError("pass_threshold must be between 0 and 1")
        self._client = client
        self._pass_threshold = pass_threshold
        self._prompt_template = prompt_template

    def score(self, case: EvaluationCase, answer: str) -> JudgeVerdict:
        prompt = self._prompt_template.format(
            question=case.question,
            reference=case.reference_answer,
            answer=answer,
        )
        try:
            reply = self._client(prompt)
        except Exception as error:  # noqa: BLE001 - surface any client failure as JudgeError
            raise JudgeError(f"model judge client failed: {error}") from error

        if not isinstance(reply, str) or not reply.strip():
            raise JudgeError("model judge returned an empty reply")

        score_match = _SCORE_PATTERN.search(reply)
        if score_match is None:
            raise JudgeError(f"model judge reply had no SCORE line: {reply!r}")
        score = max(0.0, min(1.0, float(score_match.group(1))))

        verdict_match = _VERDICT_PATTERN.search(reply)
        if verdict_match is not None:
            passed = verdict_match.group(1).lower() in {"pass", "yes"}
        else:
            passed = score >= self._pass_threshold

        return JudgeVerdict(passed=passed, score=round(score, 4), rationale=reply.strip())


def create_judge(name: str) -> AnswerJudge:
    """Build a judge by name. Only the deterministic judge is selectable here;
    the model judge needs a client and is constructed directly by callers."""
    if name == "keyword":
        return KeywordJudge()
    raise ValueError(
        f"unknown judge {name!r}; the default run supports 'keyword'. "
        "Construct ModelJudge(client=...) directly to use an LLM judge."
    )
