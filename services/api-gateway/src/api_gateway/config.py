import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_CORS_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
)


def cors_allowed_origins_from_env() -> tuple[str, ...]:
    configured_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    if configured_origins is None:
        return DEFAULT_CORS_ALLOWED_ORIGINS

    origins = tuple(
        dict.fromkeys(
            origin.strip().removesuffix("/")
            for origin in configured_origins.split(",")
            if origin.strip()
        )
    )
    if not origins:
        raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin")

    for origin in origins:
        parsed_origin = urlsplit(origin)
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.netloc
            or parsed_origin.path
            or parsed_origin.query
            or parsed_origin.fragment
            or parsed_origin.username
            or parsed_origin.password
        ):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must contain only absolute HTTP or HTTPS origins"
            )

    return origins


@dataclass(frozen=True)
class Settings:
    agent_service_url: str
    agent_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        agent_service_url = os.getenv("AGENT_SERVICE_URL", "http://agent:8001").rstrip("/")
        timeout_value = os.getenv("AGENT_REQUEST_TIMEOUT_SECONDS", "10")

        parsed_url = urlsplit(agent_service_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("AGENT_SERVICE_URL must be an absolute HTTP or HTTPS URL")

        try:
            timeout_seconds = float(timeout_value)
        except ValueError as error:
            raise ValueError("AGENT_REQUEST_TIMEOUT_SECONDS must be a number") from error

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("AGENT_REQUEST_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            agent_service_url=agent_service_url,
            agent_request_timeout_seconds=timeout_seconds,
        )
