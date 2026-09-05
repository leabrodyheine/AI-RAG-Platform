"""Build the grounded prompt the agent sends to the inference service."""

from agent_service.schemas import Citation

SYSTEM_INSTRUCTION = (
    "You investigate AI system evaluation results using only the supplied evidence. "
    "Cite each supporting source inline as [n], matching the evidence numbers below. "
    "If the evidence does not answer the question, say so plainly and do not guess."
)

_NO_EVIDENCE = "(no evidence retrieved)"


def build_grounded_prompt(question: str, citations: list[Citation]) -> str:
    """Render the question and retrieved evidence into a single prompt string.

    Every citation is listed on its own ``[n]`` line so the inference backend can
    ground its answer in a specific source and the answer can cite it by number.
    """
    lines = [SYSTEM_INSTRUCTION, "", f"Question: {question}", "", "Evidence:"]
    if citations:
        lines.extend(
            f"[{index}] {citation.title} — {citation.excerpt}"
            for index, citation in enumerate(citations, start=1)
        )
    else:
        lines.append(_NO_EVIDENCE)
    lines.extend(["", "Answer the question using only the evidence above."])
    return "\n".join(lines)
