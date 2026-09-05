"""Adapter for an OpenAI-compatible vLLM server.

vLLM serves ``POST /v1/completions`` with the OpenAI schema. The agent already
builds the full prompt, so the text-completions endpoint is a direct fit: no
chat templating is applied here. ``GET /health`` returns 200 only once the
engine has finished loading the model, so it doubles as the readiness signal.
"""

import httpx

from inference_service.backends.base import (
    GenerationResult,
    InferenceBackendUnavailableError,
)
from inference_service.backends.remote import RemoteBackend, is_token_count

_COMPLETIONS_PATH = "/v1/completions"
_HEALTH_PATH = "/health"


class VLLMBackend(RemoteBackend):
    name = "vllm"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        stop_sequences: tuple[str, ...] = (),
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            health_path=_HEALTH_PATH,
            stop_sequences=stop_sequences,
            client=client,
        )

    async def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> GenerationResult:
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if self._stop_sequences:
            payload["stop"] = list(self._stop_sequences)

        body = await self._post_json(_COMPLETIONS_PATH, payload)
        return _parse_completion(body, backend_name=self.name)


def _parse_completion(body: dict[str, object], *, backend_name: str) -> GenerationResult:
    try:
        text = body["choices"][0]["text"]  # type: ignore[index]
        usage = body["usage"]
        prompt_tokens = usage["prompt_tokens"]  # type: ignore[index]
        completion_tokens = usage["completion_tokens"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise InferenceBackendUnavailableError(
            f"the {backend_name} backend returned an unparsable completion"
        ) from error

    if not isinstance(text, str) or not text.strip():
        raise InferenceBackendUnavailableError(
            f"the {backend_name} backend returned an empty completion"
        )
    if not is_token_count(prompt_tokens) or not is_token_count(completion_tokens):
        raise InferenceBackendUnavailableError(
            f"the {backend_name} backend returned invalid token usage"
        )
    return GenerationResult(
        content=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
