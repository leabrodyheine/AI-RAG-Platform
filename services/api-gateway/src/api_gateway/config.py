import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


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
