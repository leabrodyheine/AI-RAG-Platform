"""Deterministic workflow used until retrieval and inference are connected."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DevelopmentAnswer:
    content: str
    trace_detail: str


def build_development_answer(question: str) -> DevelopmentAnswer:
    normalized_question = question.casefold()

    if any(keyword in normalized_question for keyword in ("latency", "slow", "performance")):
        return DevelopmentAnswer(
            content=(
                "The development agent classified this as a performance investigation. "
                "Retrieval and inference telemetry will be used to answer it once those "
                "services are connected."
            ),
            trace_detail="Performance question routed to the development workflow",
        )

    if any(keyword in normalized_question for keyword in ("retrieval", "cache", "citation")):
        return DevelopmentAnswer(
            content=(
                "The development agent classified this as a retrieval investigation. "
                "Document search is not connected yet, so no evidence or citations are "
                "returned in this vertical slice."
            ),
            trace_detail="Retrieval question routed to the development workflow",
        )

    return DevelopmentAnswer(
        content=(
            "The development agent received the question successfully. Retrieval and model "
            "inference will replace this deterministic response in later vertical slices."
        ),
        trace_detail="General question routed to the development workflow",
    )
