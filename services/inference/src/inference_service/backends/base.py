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

    name: str
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

    async def ready(self) -> bool:
        """Report whether the backend can serve a generation request now.

        This is model readiness, not process liveness: a remote backend returns
        ``False`` while its model server is still loading weights. It never
        raises.
        """
        ...

    async def aclose(self) -> None:
        """Release any resources the backend holds."""
        ...


class InferenceBackendError(RuntimeError):
    """Base class for failures raised by an inference backend."""


class InferenceBackendUnavailableError(InferenceBackendError):
    """The configured backend could not be reached or refused the request."""


class InferenceBackendTimeoutError(InferenceBackendError):
    """The configured backend did not respond before its timeout."""
