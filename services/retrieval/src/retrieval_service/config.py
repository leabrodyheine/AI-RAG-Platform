import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from retrieval_service.embeddings import (
    DEFAULT_SEMANTIC_MODEL,
    DEFAULT_SEMANTIC_MODEL_VERSION,
)

SUPPORTED_EMBEDDING_PROVIDERS = {"fastembed", "feature-hash"}


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
    embedding_provider: str
    embedding_model: str
    embedding_model_version: str
    embedding_cache_dir: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        configured_url = os.getenv("DATABASE_URL")
        database_url = (
            normalize_database_url(configured_url.strip())
            if configured_url is not None and configured_url.strip()
            else None
        )
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().casefold()
        if embedding_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_EMBEDDING_PROVIDERS))
            raise ValueError(f"EMBEDDING_PROVIDER must be one of: {supported}")

        embedding_model = os.getenv("EMBEDDING_MODEL", DEFAULT_SEMANTIC_MODEL).strip()
        embedding_model_version = os.getenv(
            "EMBEDDING_MODEL_VERSION", DEFAULT_SEMANTIC_MODEL_VERSION
        ).strip()
        if not embedding_model:
            raise ValueError("EMBEDDING_MODEL must not be empty")
        if not embedding_model_version:
            raise ValueError("EMBEDDING_MODEL_VERSION must not be empty")
        configured_cache_dir = os.getenv("EMBEDDING_CACHE_DIR")
        embedding_cache_dir = (
            configured_cache_dir.strip()
            if configured_cache_dir is not None and configured_cache_dir.strip()
            else None
        )

        return cls(
            database_url=database_url,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            embedding_cache_dir=embedding_cache_dir,
        )
