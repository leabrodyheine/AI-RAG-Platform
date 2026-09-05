import pytest
from agent_service.config import Settings


def test_settings_use_service_network_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "RETRIEVAL_SERVICE_URL",
        "RETRIEVAL_REQUEST_TIMEOUT_SECONDS",
        "INFERENCE_SERVICE_URL",
        "INFERENCE_REQUEST_TIMEOUT_SECONDS",
        "AGENT_WORKFLOW_MIN_RELEVANCE",
        "AGENT_WORKFLOW_MIN_RESULTS",
        "AGENT_WORKFLOW_MAX_STEPS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.retrieval_service_url == "http://retrieval:8002"
    assert settings.retrieval_request_timeout_seconds == 5
    assert settings.inference_service_url == "http://inference:8003"
    assert settings.inference_request_timeout_seconds == 15
    assert settings.workflow_min_relevance == 0.3
    assert settings.workflow_min_results == 1
    assert settings.workflow_max_steps == 4


def test_settings_read_workflow_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_WORKFLOW_MIN_RELEVANCE", "0.55")
    monkeypatch.setenv("AGENT_WORKFLOW_MIN_RESULTS", "2")
    monkeypatch.setenv("AGENT_WORKFLOW_MAX_STEPS", "6")

    settings = Settings.from_env()

    assert settings.workflow_min_relevance == 0.55
    assert settings.workflow_min_results == 2
    assert settings.workflow_max_steps == 6


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AGENT_WORKFLOW_MIN_RELEVANCE", "1.5"),
        ("AGENT_WORKFLOW_MIN_RELEVANCE", "-0.1"),
        ("AGENT_WORKFLOW_MIN_RELEVANCE", "abc"),
        ("AGENT_WORKFLOW_MIN_RESULTS", "0"),
        ("AGENT_WORKFLOW_MIN_RESULTS", "two"),
        ("AGENT_WORKFLOW_MAX_STEPS", "0"),
    ],
)
def test_settings_reject_invalid_workflow_values(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        Settings.from_env()


def test_settings_read_service_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RETRIEVAL_SERVICE_URL", "http://localhost:9002/")
    monkeypatch.setenv("RETRIEVAL_REQUEST_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("INFERENCE_SERVICE_URL", "http://localhost:9003/")
    monkeypatch.setenv("INFERENCE_REQUEST_TIMEOUT_SECONDS", "20")

    settings = Settings.from_env()

    assert settings.retrieval_service_url == "http://localhost:9002"
    assert settings.retrieval_request_timeout_seconds == 1.5
    assert settings.inference_service_url == "http://localhost:9003"
    assert settings.inference_request_timeout_seconds == 20


@pytest.mark.parametrize(
    "name",
    ["RETRIEVAL_REQUEST_TIMEOUT_SECONDS", "INFERENCE_REQUEST_TIMEOUT_SECONDS"],
)
@pytest.mark.parametrize("timeout", ["invalid", "0", "-1", "inf"])
def test_settings_reject_invalid_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    timeout: str,
) -> None:
    monkeypatch.setenv(name, timeout)

    with pytest.raises(ValueError, match=name):
        Settings.from_env()


@pytest.mark.parametrize(
    "name",
    ["RETRIEVAL_SERVICE_URL", "INFERENCE_SERVICE_URL"],
)
def test_settings_reject_invalid_service_urls(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    monkeypatch.setenv(name, "inference:8003")

    with pytest.raises(ValueError, match=name):
        Settings.from_env()
