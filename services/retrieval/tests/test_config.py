import pytest
from retrieval_service.config import Settings, normalize_database_url
from retrieval_service.embeddings import DEFAULT_SEMANTIC_MODEL, DEFAULT_SEMANTIC_MODEL_VERSION


def test_settings_disable_persistence_when_database_url_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("EMBEDDING_MODEL_VERSION", raising=False)
    monkeypatch.delenv("EMBEDDING_CACHE_DIR", raising=False)

    settings = Settings.from_env()

    assert settings.database_url is None
    assert settings.embedding_provider == "fastembed"
    assert settings.embedding_model == DEFAULT_SEMANTIC_MODEL
    assert settings.embedding_model_version == DEFAULT_SEMANTIC_MODEL_VERSION
    assert settings.embedding_cache_dir is None


def test_settings_disable_persistence_when_database_url_is_blank(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "  ")

    assert Settings.from_env().database_url is None


def test_settings_normalize_sqlalchemy_asyncpg_urls(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://rag:secret@postgres:5432/platform",
    )

    assert Settings.from_env().database_url == (
        "postgresql://rag:secret@postgres:5432/platform"
    )


@pytest.mark.parametrize(
    "database_url",
    [
        "mysql://db/platform",
        "postgresql:///platform",
        "postgresql://db",
        "not-a-url",
    ],
)
def test_database_url_requires_postgres_host_and_database(database_url: str) -> None:
    with pytest.raises(ValueError, match="PostgreSQL host and database"):
        normalize_database_url(database_url)


def test_settings_accept_the_offline_embedding_provider(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", " FEATURE-HASH ")

    assert Settings.from_env().embedding_provider == "feature-hash"


def test_settings_accept_an_explicit_model_version(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "organization/model")
    monkeypatch.setenv("EMBEDDING_MODEL_VERSION", "organization/model@revision-2")
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", " /models/embeddings ")

    settings = Settings.from_env()

    assert settings.embedding_model == "organization/model"
    assert settings.embedding_model_version == "organization/model@revision-2"
    assert settings.embedding_cache_dir == "/models/embeddings"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("EMBEDDING_PROVIDER", "unknown", "EMBEDDING_PROVIDER"),
        ("EMBEDDING_MODEL", " ", "EMBEDDING_MODEL"),
        ("EMBEDDING_MODEL_VERSION", "", "EMBEDDING_MODEL_VERSION"),
    ],
)
def test_settings_reject_invalid_embedding_configuration(
    monkeypatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        Settings.from_env()
