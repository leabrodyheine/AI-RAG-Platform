from typing import cast

from fastapi import Request

from api_gateway.clients.agent import AgentClient


def get_agent_client(request: Request) -> AgentClient:
    return cast(AgentClient, request.app.state.agent_client)
