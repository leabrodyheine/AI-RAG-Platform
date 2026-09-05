import math
import os
from dataclasses import dataclass

SUPPORTED_BACKENDS = {"deterministic"}


@dataclass(frozen=True)
class Settings:
    backend: str
    model: str
    backend_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        backend = os.getenv("INFERENCE_BACKEND", "deterministic").strip().casefold()
        if backend not in SUPPORTED_BACKENDS:
            supported = ", ".join(sorted(SUPPORTED_BACKENDS))
            raise ValueError(f"INFERENCE_BACKEND must be one of: {supported}")

        model = os.getenv("INFERENCE_MODEL", "deterministic-grounded-v1").strip()
        if not model:
            raise ValueError("INFERENCE_MODEL must not be empty")

        configured_timeout = os.getenv("INFERENCE_BACKEND_TIMEOUT_SECONDS", "30")
        try:
            backend_timeout_seconds = float(configured_timeout)
        except ValueError as error:
            raise ValueError("INFERENCE_BACKEND_TIMEOUT_SECONDS must be a number") from error
        if not math.isfinite(backend_timeout_seconds) or backend_timeout_seconds <= 0:
            raise ValueError("INFERENCE_BACKEND_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            backend=backend,
            model=model,
            backend_timeout_seconds=backend_timeout_seconds,
        )
