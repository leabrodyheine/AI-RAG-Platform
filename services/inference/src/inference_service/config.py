import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

SUPPORTED_BACKENDS = {"deterministic", "vllm", "triton"}

# Backends that reach a model server over HTTP and the environment variable that
# points at each one.
REMOTE_BACKEND_URL_ENV = {
    "vllm": "VLLM_BASE_URL",
    "triton": "TRITON_BASE_URL",
}


def _parse_base_url(name: str, raw_value: str) -> str:
    base_url = raw_value.strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP or HTTPS URL")
    return base_url


def _parse_stop_sequences(raw_value: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(part for part in (item.strip() for item in raw_value.split(",")) if part)
    )


@dataclass(frozen=True)
class Settings:
    backend: str
    model: str
    backend_timeout_seconds: float
    backend_base_url: str | None
    stop_sequences: tuple[str, ...]

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

        backend_base_url: str | None = None
        url_env = REMOTE_BACKEND_URL_ENV.get(backend)
        if url_env is not None:
            configured_url = os.getenv(url_env, "")
            if not configured_url.strip():
                raise ValueError(f"{url_env} must be set when INFERENCE_BACKEND is {backend}")
            backend_base_url = _parse_base_url(url_env, configured_url)

        stop_sequences = _parse_stop_sequences(os.getenv("INFERENCE_STOP_SEQUENCES", ""))

        return cls(
            backend=backend,
            model=model,
            backend_timeout_seconds=backend_timeout_seconds,
            backend_base_url=backend_base_url,
            stop_sequences=stop_sequences,
        )
