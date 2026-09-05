"""Shared HTTP handling for backends that call a remote model server."""

import httpx

from inference_service.backends.base import (
    InferenceBackendTimeoutError,
    InferenceBackendUnavailableError,
)


class RemoteBackend:
    """Own an HTTP client to a model server and translate its failures.

    Subclasses implement ``generate`` and map the server's request and response
    shape. Transport timeouts become ``InferenceBackendTimeoutError`` and every
    other transport, status, or decoding failure becomes
    ``InferenceBackendUnavailableError`` so the route can return a stable 503.
    """

    name: str = "remote"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        health_path: str,
        stop_sequences: tuple[str, ...] = (),
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._stop_sequences = stop_sequences
        self._health_path = health_path
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
        )

    async def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.TimeoutException as error:
            raise InferenceBackendTimeoutError(
                f"the {self.name} backend did not respond in time"
            ) from error
        except httpx.HTTPError as error:
            raise InferenceBackendUnavailableError(
                f"the {self.name} backend could not be reached"
            ) from error

        if not response.is_success:
            raise InferenceBackendUnavailableError(
                f"the {self.name} backend returned HTTP {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise InferenceBackendUnavailableError(
                f"the {self.name} backend returned a non-JSON response"
            ) from error
        if not isinstance(body, dict):
            raise InferenceBackendUnavailableError(
                f"the {self.name} backend returned an unexpected response shape"
            )
        return body

    async def ready(self) -> bool:
        try:
            response = await self._client.get(self._health_path)
        except httpx.HTTPError:
            return False
        return response.is_success

    async def aclose(self) -> None:
        await self._client.aclose()


def is_token_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
