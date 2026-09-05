from dataclasses import dataclass
from uuid import uuid4

import httpx

from agent_service.config import Settings

DEFAULT_MAX_TOKENS = 512
DEFAULT_TEMPERATURE = 0.1


class InferenceClientError(RuntimeError):
    """Base class for failures while calling the inference service."""


class InferenceConnectionError(InferenceClientError):
    """The agent could not connect to the inference service."""


class InferenceTimeoutError(InferenceClientError):
    """The inference service did not respond before the configured timeout."""


class InferenceResponseError(InferenceClientError):
    """The inference service returned an unsuccessful or malformed response."""


@dataclass(frozen=True)
class GeneratedAnswer:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int


class InferenceClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    @classmethod
    def from_settings(cls, settings: Settings) -> "InferenceClient":
        return cls(
            httpx.AsyncClient(
                base_url=settings.inference_service_url,
                timeout=settings.inference_request_timeout_seconds,
            )
        )

    @property
    def is_closed(self) -> bool:
        return self._http_client.is_closed

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        request_id: str | None = None,
    ) -> GeneratedAnswer:
        correlation_id = request_id or str(uuid4())
        try:
            response = await self._http_client.post(
                "/generate",
                json={
                    "prompt": prompt,
                    "maxTokens": max_tokens,
                    "temperature": temperature,
                },
                headers={"X-Request-ID": correlation_id},
            )
        except httpx.TimeoutException as error:
            raise InferenceTimeoutError("The inference request timed out") from error
        except httpx.NetworkError as error:
            raise InferenceConnectionError(
                "The inference service could not be reached"
            ) from error
        except httpx.TransportError as error:
            raise InferenceResponseError(
                "The inference response could not be read"
            ) from error

        if response.status_code == httpx.codes.GATEWAY_TIMEOUT:
            raise InferenceTimeoutError("The inference service reported an upstream timeout")

        if not response.is_success:
            raise InferenceResponseError(
                f"The inference service returned HTTP {response.status_code}"
            )

        try:
            return _parse_generated_answer(response.json())
        except (KeyError, TypeError, ValueError) as error:
            raise InferenceResponseError(
                "The inference service returned an invalid generation payload"
            ) from error

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _parse_generated_answer(payload: object) -> GeneratedAnswer:
    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")

    content = payload["content"]
    model = payload["model"]
    usage = payload["usage"]
    if not isinstance(content, str) or not content:
        raise ValueError("content must be a non-empty string")
    if not isinstance(model, str) or not model:
        raise ValueError("model must be a non-empty string")
    if not isinstance(usage, dict):
        raise TypeError("usage must be an object")

    prompt_tokens = usage["promptTokens"]
    completion_tokens = usage["completionTokens"]
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
        raise ValueError("promptTokens must be an integer")
    if not isinstance(completion_tokens, int) or isinstance(completion_tokens, bool):
        raise ValueError("completionTokens must be an integer")

    return GeneratedAnswer(
        content=content,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
