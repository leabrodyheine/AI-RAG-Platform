"""A CPU-only backend that synthesises a grounded answer without a model.

The deterministic backend lets the full request path run in unit tests and on
developer machines. It never downloads weights, never uses a GPU, and returns
the same answer for the same prompt. It reads only the prompt it is given: the
agent builds that prompt from the question and retrieved evidence, listing each
source on its own ``[n]`` line.
"""

import re

from inference_service.backends.base import GenerationResult

EVIDENCE_LINE = re.compile(r"^\s*\[(\d+)\]\s+(.*\S)\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_INSUFFICIENT_EVIDENCE = (
    "The retrieved evidence does not support an answer to this question."
)


class DeterministicBackend:
    """Compose a grounded answer from the evidence lines in the prompt."""

    name = "deterministic"

    def __init__(self, model: str) -> None:
        self.model = model

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        answer = _compose_answer(prompt)
        answer = _limit_tokens(answer, max_tokens)
        return GenerationResult(
            content=answer,
            prompt_tokens=_count_tokens(prompt),
            completion_tokens=_count_tokens(answer),
        )

    async def ready(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def _compose_answer(prompt: str) -> str:
    evidence = [
        match.group(2)
        for line in prompt.splitlines()
        if (match := EVIDENCE_LINE.match(line))
    ]
    if not evidence:
        return _INSUFFICIENT_EVIDENCE

    strongest = evidence[0]
    _, separator, detail = strongest.partition(" — ")
    claim = detail if separator else strongest
    first_sentence = SENTENCE_END.split(claim.strip(), maxsplit=1)[0]
    return f"Based on the retrieved evidence, {first_sentence} [1]"


def _limit_tokens(text: str, max_tokens: int) -> str:
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text
    return " ".join(tokens[:max_tokens])


def _count_tokens(text: str) -> int:
    return len(text.split())
