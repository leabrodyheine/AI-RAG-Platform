from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from rag_observability import client_event_hooks

from api_gateway.config import Settings

JsonObject = dict[str, Any]


class AgentClientError(RuntimeError):
    """Base class for failures while calling the agent service."""


class AgentConnectionError(AgentClientError):
    """The gateway could not connect to the agent service."""


class AgentTimeoutError(AgentClientError):
    """The agent service did not respond before the configured timeout."""


class AgentResponseError(AgentClientError):
    """The agent service returned an unsuccessful or malformed response."""


@dataclass(frozen=True)
class AgentAnswer:
    payload: JsonObject
    request_id: str


class AgentClient:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client

    @classmethod
    def from_settings(cls, settings: Settings) -> "AgentClient":
        return cls(
            httpx.AsyncClient(
                base_url=settings.agent_service_url,
                timeout=settings.agent_request_timeout_seconds,
                event_hooks=client_event_hooks("api-gateway", "agent"),
            )
        )

    @property
    def is_closed(self) -> bool:
        return self._http_client.is_closed

    async def answer(self, question: str, request_id: str | None = None) -> AgentAnswer:
        correlation_id = request_id or str(uuid4())

        try:
            response = await self._http_client.post(
                "/answer",
                json={"question": question},
                headers={"X-Request-ID": correlation_id},
            )
        except httpx.TimeoutException as error:
            raise AgentTimeoutError("The agent request timed out") from error
        except httpx.NetworkError as error:
            raise AgentConnectionError("The agent service could not be reached") from error
        except httpx.TransportError as error:
            raise AgentResponseError("The agent response could not be read") from error

        if response.status_code == httpx.codes.GATEWAY_TIMEOUT:
            raise AgentTimeoutError("The agent service reported an upstream timeout")

        if not response.is_success:
            raise AgentResponseError(
                f"The agent service returned HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise AgentResponseError("The agent service returned invalid JSON") from error

        if not _is_answer_payload(payload):
            raise AgentResponseError("The agent service returned an invalid answer payload")

        return AgentAnswer(payload=payload, request_id=correlation_id)

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _is_answer_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False

    return (
        isinstance(payload.get("content"), str)
        and isinstance(payload.get("citations"), list)
        and isinstance(payload.get("trace"), list)
        and isinstance(payload.get("totalDurationMs"), int)
    )
