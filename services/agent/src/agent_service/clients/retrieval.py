from uuid import uuid4

import httpx
from pydantic import ValidationError
from rag_observability import client_event_hooks

from agent_service.config import Settings
from agent_service.schemas import Citation


class RetrievalClientError(RuntimeError):
    """Base class for failures while calling the retrieval service."""


class RetrievalConnectionError(RetrievalClientError):
    """The agent could not connect to the retrieval service."""


class RetrievalTimeoutError(RetrievalClientError):
    """The retrieval service did not respond before the configured timeout."""


class RetrievalResponseError(RetrievalClientError):
    """The retrieval service returned an unsuccessful or malformed response."""


class RetrievalClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetrievalClient":
        return cls(
            httpx.AsyncClient(
                base_url=settings.retrieval_service_url,
                timeout=settings.retrieval_request_timeout_seconds,
                event_hooks=client_event_hooks("agent", "retrieval"),
            )
        )

    @property
    def is_closed(self) -> bool:
        return self._http_client.is_closed

    async def search(
        self,
        query: str,
        *,
        top_k: int = 3,
        request_id: str | None = None,
    ) -> list[Citation]:
        correlation_id = request_id or str(uuid4())
        try:
            response = await self._http_client.post(
                "/search",
                json={"query": query, "topK": top_k},
                headers={"X-Request-ID": correlation_id},
            )
        except httpx.TimeoutException as error:
            raise RetrievalTimeoutError("The retrieval request timed out") from error
        except httpx.NetworkError as error:
            raise RetrievalConnectionError("The retrieval service could not be reached") from error
        except httpx.TransportError as error:
            raise RetrievalResponseError("The retrieval response could not be read") from error

        if not response.is_success:
            raise RetrievalResponseError(
                f"The retrieval service returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
            raw_results = payload["results"]
            if not isinstance(raw_results, list):
                raise TypeError("results must be a list")
            return [Citation.model_validate(result) for result in raw_results]
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise RetrievalResponseError(
                "The retrieval service returned an invalid search payload"
            ) from error

    async def aclose(self) -> None:
        await self._http_client.aclose()
