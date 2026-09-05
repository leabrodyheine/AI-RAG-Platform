from typing import cast

from fastapi import Request

from agent_service.clients.retrieval import RetrievalClient


def get_retrieval_client(request: Request) -> RetrievalClient:
    return cast(RetrievalClient, request.app.state.retrieval_client)
