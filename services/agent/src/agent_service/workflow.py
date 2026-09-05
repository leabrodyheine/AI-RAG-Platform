"""Evidence-grounded workflow used until model inference is connected."""

from dataclasses import dataclass

from agent_service.schemas import Citation


@dataclass(frozen=True)
class DevelopmentAnswer:
    content: str
    trace_detail: str


def build_development_answer(
    question: str,
    citations: list[Citation] | None = None,
) -> DevelopmentAnswer:
    evidence = citations or []
    normalized_question = question.casefold()

    if any(keyword in normalized_question for keyword in ("latency", "slow", "performance")):
        category = "performance"
    elif any(keyword in normalized_question for keyword in ("retrieval", "cache", "citation")):
        category = "retrieval"
    else:
        category = "general"

    if evidence:
        strongest_evidence = evidence[0]
        return DevelopmentAnswer(
            content=(
                f"The strongest evidence for this {category} investigation comes from "
                f"{strongest_evidence.title}: {strongest_evidence.excerpt}"
            ),
            trace_detail=(
                f"{category.capitalize()} answer grounded in {len(evidence)} retrieved "
                f"source{'s' if len(evidence) != 1 else ''}"
            ),
        )

    return DevelopmentAnswer(
        content=(
            f"No matching evaluation evidence was found for this {category} investigation. "
            "Try asking about retrieval latency, caching, inference performance, or answer quality."
        ),
        trace_detail=f"{category.capitalize()} question completed without matching evidence",
    )
