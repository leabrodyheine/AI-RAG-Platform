from time import perf_counter_ns
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse

from agent_service.clients.retrieval import (
    RetrievalClient,
    RetrievalClientError,
    RetrievalTimeoutError,
)
from agent_service.dependencies import get_retrieval_client
from agent_service.schemas import ChatRequest, ChatResponse, TraceStep
from agent_service.workflow import build_development_answer

router = APIRouter(tags=["chat"])


@router.post("/answer", response_model=ChatResponse)
async def answer_question(
    payload: ChatRequest,
    response: Response,
    retrieval_client: Annotated[RetrievalClient, Depends(get_retrieval_client)],
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
) -> ChatResponse | JSONResponse:
    request_id = caller_request_id or str(uuid4())
    started_at = perf_counter_ns()
    retrieval_started_at = perf_counter_ns()
    try:
        citations = await retrieval_client.search(
            payload.question,
            request_id=request_id,
        )
    except RetrievalTimeoutError:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"detail": "The retrieval service did not respond in time."},
            headers={"X-Request-ID": request_id},
        )
    except RetrievalClientError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "The retrieval service is temporarily unavailable."},
            headers={"X-Request-ID": request_id},
        )

    retrieval_duration_ms = (perf_counter_ns() - retrieval_started_at) // 1_000_000
    synthesis_started_at = perf_counter_ns()
    result = build_development_answer(payload.question, citations)
    synthesis_duration_ms = (perf_counter_ns() - synthesis_started_at) // 1_000_000
    total_duration_ms = (perf_counter_ns() - started_at) // 1_000_000
    response.headers["X-Request-ID"] = request_id
    source_label = "source" if len(citations) == 1 else "sources"

    return ChatResponse(
        content=result.content,
        citations=citations,
        trace=[
            TraceStep(
                label="Retrieve",
                detail=f"{len(citations)} matching evaluation {source_label}",
                duration_ms=retrieval_duration_ms,
            ),
            TraceStep(
                label="Synthesize",
                detail=result.trace_detail,
                duration_ms=synthesis_duration_ms,
            ),
        ],
        total_duration_ms=total_duration_ms,
    )
