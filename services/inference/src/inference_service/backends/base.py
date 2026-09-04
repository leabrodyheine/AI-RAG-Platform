from typing import Protocol


class InferenceBackend(Protocol):
    """Interface implemented by each inference backend adapter."""

    async def generate(self, prompt: str) -> str:
        """Generate text for a fully constructed prompt."""
        ...
