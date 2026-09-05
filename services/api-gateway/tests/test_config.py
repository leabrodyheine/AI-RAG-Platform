import pytest
from api_gateway.config import (
    DEFAULT_CORS_ALLOWED_ORIGINS,
    Settings,
    cors_allowed_origins_from_env,
)


def test_settings_read_agent_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SERVICE_URL", "http://localhost:9001/")
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_SECONDS", "2.5")

    settings = Settings.from_env()

    assert settings.agent_service_url == "http://localhost:9001"
    assert settings.agent_request_timeout_seconds == 2.5


@pytest.mark.parametrize("timeout", ["invalid", "0", "-1", "inf"])
def test_settings_reject_invalid_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("AGENT_REQUEST_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match="AGENT_REQUEST_TIMEOUT_SECONDS"):
        Settings.from_env()


def test_settings_reject_invalid_agent_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_SERVICE_URL", "agent:8001")

    with pytest.raises(ValueError, match="AGENT_SERVICE_URL"):
        Settings.from_env()


def test_cors_origins_default_to_local_web_servers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert cors_allowed_origins_from_env() == DEFAULT_CORS_ALLOWED_ORIGINS


def test_cors_origins_are_normalized_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        " https://web.example.com/,http://localhost:4173,https://web.example.com ",
    )

    assert cors_allowed_origins_from_env() == (
        "https://web.example.com",
        "http://localhost:4173",
    )


@pytest.mark.parametrize(
    "origins",
    ["", "*", "web.example.com", "https://web.example.com/path"],
)
def test_cors_origins_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    origins: str,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", origins)

    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        cors_allowed_origins_from_env()
