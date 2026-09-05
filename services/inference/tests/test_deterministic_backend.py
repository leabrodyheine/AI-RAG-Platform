import pytest
from inference_service.backends import DeterministicBackend, create_backend
from inference_service.config import Settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def grounded_prompt(*evidence: str) -> str:
    lines = ["Answer using only the evidence.", "", "Question: What is slow?", "", "Evidence:"]
    lines.extend(f"[{index}] {text}" for index, text in enumerate(evidence, start=1))
    return "\n".join(lines)


@pytest.mark.anyio
async def test_backend_grounds_the_answer_in_the_first_evidence_line() -> None:
    backend = DeterministicBackend(model="deterministic-grounded-v1")
    prompt = grounded_prompt(
        "Retrieval benchmark — Cache misses raised p95 to 391 ms. A rebuild helped.",
        "Cache report — Hit rate fell to 40 percent.",
    )

    result = await backend.generate(prompt, max_tokens=512, temperature=0.1)

    assert result.content == (
        "Based on the retrieved evidence, Cache misses raised p95 to 391 ms. [1]"
    )
    assert result.prompt_tokens == len(prompt.split())
    assert result.completion_tokens == len(result.content.split())


@pytest.mark.anyio
async def test_backend_reports_when_no_evidence_is_present() -> None:
    backend = DeterministicBackend(model="deterministic-grounded-v1")

    result = await backend.generate(
        "Question: What is slow?\n\nEvidence:\n(no evidence retrieved)",
        max_tokens=64,
        temperature=0.0,
    )

    assert result.content == (
        "The retrieved evidence does not support an answer to this question."
    )
    assert result.completion_tokens == len(result.content.split())


@pytest.mark.anyio
async def test_backend_is_deterministic_and_honours_max_tokens() -> None:
    backend = DeterministicBackend(model="deterministic-grounded-v1")
    prompt = grounded_prompt("Result — one two three four five six seven eight nine ten.")

    first = await backend.generate(prompt, max_tokens=4, temperature=1.5)
    second = await backend.generate(prompt, max_tokens=4, temperature=0.0)

    assert first == second
    assert first.content == "Based on the retrieved"
    assert first.completion_tokens == 4


def settings(**overrides: object) -> Settings:
    base = {
        "backend": "deterministic",
        "model": "local-test-model",
        "backend_timeout_seconds": 30,
        "backend_base_url": None,
        "stop_sequences": (),
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_create_backend_builds_the_deterministic_backend() -> None:
    backend = create_backend(settings(backend="deterministic"))

    assert isinstance(backend, DeterministicBackend)
    assert backend.model == "local-test-model"


def test_create_backend_rejects_an_unknown_backend() -> None:
    with pytest.raises(ValueError, match="unsupported inference backend"):
        create_backend(settings(backend="mystery"))
