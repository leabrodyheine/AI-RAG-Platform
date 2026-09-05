import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from retrieval_service.embeddings import (
    DEFAULT_SEMANTIC_MODEL,
    default_semantic_model_version,
)

SUPPORTED_EMBEDDING_PROVIDERS = {"fastembed", "feature-hash"}
DEFAULT_CACHE_TTL_SECONDS = 60


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


def normalize_redis_url(redis_url: str) -> str:
    normalized_url = redis_url.rstrip("/")
    parsed_url = urlsplit(normalized_url)
    if parsed_url.scheme not in {"redis", "rediss"} or not parsed_url.hostname:
        raise ValueError("REDIS_URL must be an absolute Redis URL")
    return normalized_url


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    redis_url: str | None
    cache_ttl_seconds: int
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
        configured_redis_url = os.getenv("REDIS_URL")
        redis_url = (
            normalize_redis_url(configured_redis_url.strip())
            if configured_redis_url is not None and configured_redis_url.strip()
            else None
        )
        configured_ttl = os.getenv("RETRIEVAL_CACHE_TTL_SECONDS", str(DEFAULT_CACHE_TTL_SECONDS))
        try:
            cache_ttl_seconds = int(configured_ttl)
        except ValueError as error:
            raise ValueError("RETRIEVAL_CACHE_TTL_SECONDS must be an integer") from error
        if not 1 <= cache_ttl_seconds <= 86_400:
            raise ValueError("RETRIEVAL_CACHE_TTL_SECONDS must be between 1 and 86400")
        embedding_provider = os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().casefold()
        if embedding_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_EMBEDDING_PROVIDERS))
            raise ValueError(f"EMBEDDING_PROVIDER must be one of: {supported}")

        embedding_model = os.getenv("EMBEDDING_MODEL", DEFAULT_SEMANTIC_MODEL).strip()
        configured_model_version = os.getenv("EMBEDDING_MODEL_VERSION")
        embedding_model_version = (
            configured_model_version.strip()
            if configured_model_version is not None
            else default_semantic_model_version(embedding_model)
        )
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
            redis_url=redis_url,
            cache_ttl_seconds=cache_ttl_seconds,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_model_version=embedding_model_version,
            embedding_cache_dir=embedding_cache_dir,
        )
