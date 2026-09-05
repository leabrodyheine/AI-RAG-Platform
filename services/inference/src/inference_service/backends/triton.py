"""Adapter for a Triton Inference Server running a TensorRT-LLM model.

Triton exposes the KServe v2 convenience endpoint
``POST /v2/models/{model}/generate``, which accepts a text prompt and returns
``text_output`` without the caller assembling raw inference tensors. That
endpoint does not report token counts, so prompt and completion tokens are
approximated by whitespace splitting, consistent with the deterministic
backend. ``GET /v2/models/{model}/ready`` is model-level readiness, distinct
from the server-level ``/v2/health/ready``.
"""

from urllib.parse import quote

import httpx

from inference_service.backends.base import (
    GenerationResult,
    InferenceBackendUnavailableError,
)
from inference_service.backends.remote import RemoteBackend


class TritonBackend(RemoteBackend):
    name = "triton"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        stop_sequences: tuple[str, ...] = (),
        client: httpx.AsyncClient | None = None,
    ) -> None:
        encoded_model = quote(model, safe="")
        self._generate_path = f"/v2/models/{encoded_model}/generate"
        super().__init__(
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            health_path=f"/v2/models/{encoded_model}/ready",
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
            "text_input": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if self._stop_sequences:
            payload["stop_words"] = list(self._stop_sequences)

        body = await self._post_json(self._generate_path, payload)
        return _parse_generation(body, prompt=prompt, backend_name=self.name)


def _parse_generation(
    body: dict[str, object],
    *,
    prompt: str,
    backend_name: str,
) -> GenerationResult:
    text = body.get("text_output")
    if not isinstance(text, str) or not text.strip():
        raise InferenceBackendUnavailableError(
            f"the {backend_name} backend returned no text output"
        )
    return GenerationResult(
        content=text,
        prompt_tokens=len(prompt.split()),
        completion_tokens=len(text.split()),
    )
