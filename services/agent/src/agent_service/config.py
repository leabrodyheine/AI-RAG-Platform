import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def _service_url_from_env(name: str, default: str) -> str:
    service_url = os.getenv(name, default).rstrip("/")
    parsed_url = urlsplit(service_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError(f"{name} must be an absolute HTTP or HTTPS URL")
    return service_url


def _timeout_from_env(name: str, default: str) -> float:
    try:
        timeout_seconds = float(os.getenv(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return timeout_seconds


def _float_from_env(name: str, default: str, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _int_from_env(name: str, default: str, *, minimum: int) -> int:
    try:
        value = int(os.getenv(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    retrieval_service_url: str
    retrieval_request_timeout_seconds: float
    inference_service_url: str
    inference_request_timeout_seconds: float
    workflow_min_relevance: float
    workflow_min_results: int
    workflow_max_steps: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            retrieval_service_url=_service_url_from_env(
                "RETRIEVAL_SERVICE_URL", "http://retrieval:8002"
            ),
            retrieval_request_timeout_seconds=_timeout_from_env(
                "RETRIEVAL_REQUEST_TIMEOUT_SECONDS", "5"
            ),
            inference_service_url=_service_url_from_env(
                "INFERENCE_SERVICE_URL", "http://inference:8003"
            ),
            inference_request_timeout_seconds=_timeout_from_env(
                "INFERENCE_REQUEST_TIMEOUT_SECONDS", "15"
            ),
            workflow_min_relevance=_float_from_env(
                "AGENT_WORKFLOW_MIN_RELEVANCE", "0.3", minimum=0.0, maximum=1.0
            ),
            workflow_min_results=_int_from_env(
                "AGENT_WORKFLOW_MIN_RESULTS", "1", minimum=1
            ),
            workflow_max_steps=_int_from_env(
                "AGENT_WORKFLOW_MAX_STEPS", "4", minimum=1
            ),
        )
