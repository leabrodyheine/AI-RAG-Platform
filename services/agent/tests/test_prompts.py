from agent_service.prompts import SYSTEM_INSTRUCTION, build_grounded_prompt
from agent_service.schemas import Citation


def citation(index: int) -> Citation:
    return Citation(
        id=f"evidence-{index}",
        title=f"Benchmark run #{index}",
        source=f"evaluation/performance/run-{index}.json",
        excerpt=f"Measured detail number {index}.",
        relevance=0.9,
    )


def test_prompt_lists_numbered_evidence_under_the_instruction() -> None:
    prompt = build_grounded_prompt(
        "What is driving p95 latency?",
        [citation(1), citation(2)],
    )

    assert prompt.startswith(SYSTEM_INSTRUCTION)
    assert "Question: What is driving p95 latency?" in prompt
    assert "[1] Benchmark run #1 — Measured detail number 1." in prompt
    assert "[2] Benchmark run #2 — Measured detail number 2." in prompt
    assert prompt.rstrip().endswith("Answer the question using only the evidence above.")


def test_prompt_marks_the_absence_of_evidence() -> None:
    prompt = build_grounded_prompt("Unrelated question", [])

    assert "Evidence:\n(no evidence retrieved)" in prompt
    assert "[1]" not in prompt
