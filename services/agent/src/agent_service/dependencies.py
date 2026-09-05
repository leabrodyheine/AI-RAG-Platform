from typing import cast

from fastapi import Request

from agent_service.clients.inference import InferenceClient
from agent_service.clients.retrieval import RetrievalClient
from agent_service.workflow import WorkflowConfig


def get_retrieval_client(request: Request) -> RetrievalClient:
    return cast(RetrievalClient, request.app.state.retrieval_client)


def get_inference_client(request: Request) -> InferenceClient:
    return cast(InferenceClient, request.app.state.inference_client)


def get_workflow_config(request: Request) -> WorkflowConfig:
    return cast(
        WorkflowConfig,
        getattr(request.app.state, "workflow_config", None) or WorkflowConfig(),
    )
