import pytest
from retrieval_service.config import Settings, normalize_database_url


def test_settings_disable_persistence_when_database_url_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert Settings.from_env().database_url is None


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
