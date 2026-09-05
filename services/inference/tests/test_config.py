import pytest
from inference_service.config import Settings


def test_settings_use_cpu_safe_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "INFERENCE_BACKEND",
        "INFERENCE_MODEL",
        "INFERENCE_BACKEND_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.backend == "deterministic"
    assert settings.model == "deterministic-grounded-v1"
    assert settings.backend_timeout_seconds == 30


def test_settings_read_inference_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", " DETERMINISTIC ")
    monkeypatch.setenv("INFERENCE_MODEL", "local-test-model")
    monkeypatch.setenv("INFERENCE_BACKEND_TIMEOUT_SECONDS", "4.5")

    settings = Settings.from_env()

    assert settings.backend == "deterministic"
    assert settings.model == "local-test-model"
    assert settings.backend_timeout_seconds == 4.5


@pytest.mark.parametrize("backend", ["", "vllm", "unknown"])
def test_settings_reject_unsupported_backends(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", backend)

    with pytest.raises(ValueError, match="INFERENCE_BACKEND"):
        Settings.from_env()


def test_settings_reject_empty_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_MODEL", "  ")

    with pytest.raises(ValueError, match="INFERENCE_MODEL"):
        Settings.from_env()


@pytest.mark.parametrize("timeout", ["invalid", "0", "-1", "inf"])
def test_settings_reject_invalid_backend_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match="INFERENCE_BACKEND_TIMEOUT_SECONDS"):
        Settings.from_env()
