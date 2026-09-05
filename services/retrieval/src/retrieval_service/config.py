import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def normalize_database_url(database_url: str) -> str:
    normalized_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed_url = urlsplit(normalized_url)
    if (
        parsed_url.scheme not in {"postgres", "postgresql"}
        or not parsed_url.hostname
        or not parsed_url.path.strip("/")
    ):
        raise ValueError("DATABASE_URL must identify a PostgreSQL host and database")
    return normalized_url


@dataclass(frozen=True)
class Settings:
    database_url: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        configured_url = os.getenv("DATABASE_URL")
        if configured_url is None or not configured_url.strip():
            return cls(database_url=None)
        return cls(database_url=normalize_database_url(configured_url.strip()))
