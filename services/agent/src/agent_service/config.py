import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    retrieval_service_url: str
    retrieval_request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        service_url = os.getenv("RETRIEVAL_SERVICE_URL", "http://retrieval:8002").rstrip("/")
        timeout_value = os.getenv("RETRIEVAL_REQUEST_TIMEOUT_SECONDS", "5")

        parsed_url = urlsplit(service_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("RETRIEVAL_SERVICE_URL must be an absolute HTTP or HTTPS URL")

        try:
            timeout_seconds = float(timeout_value)
        except ValueError as error:
            raise ValueError("RETRIEVAL_REQUEST_TIMEOUT_SECONDS must be a number") from error

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("RETRIEVAL_REQUEST_TIMEOUT_SECONDS must be greater than zero")

        return cls(
            retrieval_service_url=service_url,
            retrieval_request_timeout_seconds=timeout_seconds,
        )
