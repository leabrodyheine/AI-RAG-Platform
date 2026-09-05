"""Adapters for supported model-serving backends."""

from inference_service.backends.base import (
    GenerationResult,
    InferenceBackend,
    InferenceBackendError,
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)
from inference_service.backends.deterministic import DeterministicBackend
from inference_service.backends.vllm import VLLMBackend
from inference_service.config import Settings

__all__ = [
    "DeterministicBackend",
    "GenerationResult",
    "InferenceBackend",
    "InferenceBackendError",
    "InferenceBackendTimeoutError",
    "InferenceBackendUnavailableError",
    "VLLMBackend",
    "create_backend",
]


def create_backend(settings: Settings) -> InferenceBackend:
    """Build the backend named by the service configuration."""
    if settings.backend == "deterministic":
        return DeterministicBackend(model=settings.model)
    if settings.backend == "vllm":
        return VLLMBackend(
            base_url=_require_base_url(settings),
            model=settings.model,
            timeout_seconds=settings.backend_timeout_seconds,
            stop_sequences=settings.stop_sequences,
        )
    raise ValueError(f"unsupported inference backend: {settings.backend}")


def _require_base_url(settings: Settings) -> str:
    if settings.backend_base_url is None:
        raise ValueError(f"{settings.backend} backend requires a configured base URL")
    return settings.backend_base_url
