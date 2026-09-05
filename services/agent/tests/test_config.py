import pytest
from agent_service.config import Settings


def test_settings_read_retrieval_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_SERVICE_URL", "http://localhost:9002/")
    monkeypatch.setenv("RETRIEVAL_REQUEST_TIMEOUT_SECONDS", "1.5")

    settings = Settings.from_env()

    assert settings.retrieval_service_url == "http://localhost:9002"
    assert settings.retrieval_request_timeout_seconds == 1.5


@pytest.mark.parametrize("timeout", ["invalid", "0", "-1", "inf"])
def test_settings_reject_invalid_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("RETRIEVAL_REQUEST_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match="RETRIEVAL_REQUEST_TIMEOUT_SECONDS"):
        Settings.from_env()


def test_settings_reject_invalid_retrieval_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_SERVICE_URL", "retrieval:8002")

    with pytest.raises(ValueError, match="RETRIEVAL_SERVICE_URL"):
        Settings.from_env()
