from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    """Text produced by a backend together with its token accounting."""

    content: str
    prompt_tokens: int
    completion_tokens: int


class InferenceBackend(Protocol):
    """Interface implemented by each inference backend adapter."""

    model: str

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        """Generate text for a fully constructed prompt."""
        ...


class InferenceBackendError(RuntimeError):
    """Base class for failures raised by an inference backend."""


class InferenceBackendUnavailableError(InferenceBackendError):
    """The configured backend could not be reached or refused the request."""


class InferenceBackendTimeoutError(InferenceBackendError):
    """The configured backend did not respond before its timeout."""
