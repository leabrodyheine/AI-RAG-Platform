import pytest
from api_gateway.config import Settings


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
