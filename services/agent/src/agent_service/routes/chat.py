from time import perf_counter_ns
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse
from rag_observability import current_request_id

from agent_service.clients.inference import (
    InferenceClient,
    InferenceClientError,
    InferenceTimeoutError,
)
from agent_service.clients.retrieval import (
    RetrievalClient,
    RetrievalClientError,
    RetrievalTimeoutError,
)
from agent_service.dependencies import (
    get_inference_client,
    get_retrieval_client,
    get_workflow_config,
)
from agent_service.schemas import ChatRequest, ChatResponse
from agent_service.workflow import WorkflowConfig, run_workflow

router = APIRouter(tags=["chat"])


@router.post("/answer", response_model=ChatResponse)
async def answer_question(
    payload: ChatRequest,
    response: Response,
    retrieval_client: Annotated[RetrievalClient, Depends(get_retrieval_client)],
    inference_client: Annotated[InferenceClient, Depends(get_inference_client)],
    workflow_config: Annotated[WorkflowConfig, Depends(get_workflow_config)],
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
) -> ChatResponse | JSONResponse:
    request_id = caller_request_id or current_request_id() or str(uuid4())
    started_at = perf_counter_ns()

    try:
        result = await run_workflow(
            payload.question,
            retrieval_client=retrieval_client,
            inference_client=inference_client,
            config=workflow_config,
            request_id=request_id,
        )
    except RetrievalTimeoutError:
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "The retrieval service did not respond in time.",
            request_id,
        )
    except RetrievalClientError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The retrieval service is temporarily unavailable.",
            request_id,
        )
    except InferenceTimeoutError:
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "The inference service did not respond in time.",
            request_id,
        )
    except InferenceClientError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The inference service is temporarily unavailable.",
            request_id,
        )

    total_duration_ms = (perf_counter_ns() - started_at) // 1_000_000
    response.headers["X-Request-ID"] = request_id
    return ChatResponse(
        content=result.content,
        citations=result.citations,
        trace=result.trace,
        total_duration_ms=total_duration_ms,
    )


def _error_response(status_code: int, detail: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"X-Request-ID": request_id},
    )
