import pytest
from inference_service.config import Settings

_ALL_ENV = (
    "INFERENCE_BACKEND",
    "INFERENCE_MODEL",
    "INFERENCE_BACKEND_TIMEOUT_SECONDS",
    "INFERENCE_STOP_SEQUENCES",
    "VLLM_BASE_URL",
    "TRITON_BASE_URL",
)


@pytest.fixture(autouse=True)
def clear_inference_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_ENV:
        monkeypatch.delenv(name, raising=False)


def test_settings_use_cpu_safe_defaults() -> None:
    settings = Settings.from_env()

    assert settings.backend == "deterministic"
    assert settings.model == "deterministic-grounded-v1"
    assert settings.backend_timeout_seconds == 30
    assert settings.backend_base_url is None
    assert settings.stop_sequences == ()


def test_settings_read_inference_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", " DETERMINISTIC ")
    monkeypatch.setenv("INFERENCE_MODEL", "local-test-model")
    monkeypatch.setenv("INFERENCE_BACKEND_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("INFERENCE_STOP_SEQUENCES", " </s> , User: , </s> , ")

    settings = Settings.from_env()

    assert settings.backend == "deterministic"
    assert settings.model == "local-test-model"
    assert settings.backend_timeout_seconds == 4.5
    assert settings.stop_sequences == ("</s>", "User:")


def test_settings_resolve_the_vllm_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm:8000/")

    settings = Settings.from_env()

    assert settings.backend == "vllm"
    assert settings.backend_base_url == "http://vllm:8000"


def test_settings_resolve_the_triton_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", "triton")
    monkeypatch.setenv("TRITON_BASE_URL", "http://triton:8000")

    settings = Settings.from_env()

    assert settings.backend == "triton"
    assert settings.backend_base_url == "http://triton:8000"


@pytest.mark.parametrize("backend", ["", "unknown", "vLLM-1"])
def test_settings_reject_unsupported_backends(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", backend)

    with pytest.raises(ValueError, match="INFERENCE_BACKEND"):
        Settings.from_env()


@pytest.mark.parametrize(
    ("backend", "url_env"),
    [("vllm", "VLLM_BASE_URL"), ("triton", "TRITON_BASE_URL")],
)
def test_settings_require_a_base_url_for_remote_backends(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    url_env: str,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", backend)

    with pytest.raises(ValueError, match=url_env):
        Settings.from_env()


@pytest.mark.parametrize(
    ("backend", "url_env"),
    [("vllm", "VLLM_BASE_URL"), ("triton", "TRITON_BASE_URL")],
)
def test_settings_reject_relative_base_urls(
    monkeypatch: pytest.MonkeyPatch,
    backend: str,
    url_env: str,
) -> None:
    monkeypatch.setenv("INFERENCE_BACKEND", backend)
    monkeypatch.setenv(url_env, "vllm:8000")

    with pytest.raises(ValueError, match=url_env):
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
