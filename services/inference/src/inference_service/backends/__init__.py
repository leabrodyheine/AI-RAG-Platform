"""Adapters for supported model-serving backends."""

from inference_service.backends.base import (
    GenerationResult,
    InferenceBackend,
    InferenceBackendError,
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)
from inference_service.backends.deterministic import DeterministicBackend
from inference_service.config import Settings

__all__ = [
    "DeterministicBackend",
    "GenerationResult",
    "InferenceBackend",
    "InferenceBackendError",
    "InferenceBackendTimeoutError",
    "InferenceBackendUnavailableError",
    "create_backend",
]


def create_backend(settings: Settings) -> InferenceBackend:
    """Build the backend named by the service configuration."""
    if settings.backend == "deterministic":
        return DeterministicBackend(model=settings.model)
    raise ValueError(f"unsupported inference backend: {settings.backend}")
