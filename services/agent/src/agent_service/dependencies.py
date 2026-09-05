from typing import cast

from fastapi import Request

from agent_service.clients.inference import InferenceClient
from agent_service.clients.retrieval import RetrievalClient


def get_retrieval_client(request: Request) -> RetrievalClient:
    return cast(RetrievalClient, request.app.state.retrieval_client)


def get_inference_client(request: Request) -> InferenceClient:
    return cast(InferenceClient, request.app.state.inference_client)
