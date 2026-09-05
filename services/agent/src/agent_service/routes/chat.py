from time import perf_counter_ns

from fastapi import APIRouter

from agent_service.schemas import ChatRequest, ChatResponse, TraceStep
from agent_service.workflow import build_development_answer

router = APIRouter(tags=["chat"])


@router.post("/answer", response_model=ChatResponse)
async def answer_question(request: ChatRequest) -> ChatResponse:
    started_at = perf_counter_ns()
    result = build_development_answer(request.question)
    duration_ms = (perf_counter_ns() - started_at) // 1_000_000

    return ChatResponse(
        content=result.content,
        citations=[],
        trace=[
            TraceStep(
                label="Agent",
                detail=result.trace_detail,
                duration_ms=duration_ms,
            )
        ],
        total_duration_ms=duration_ms,
    )
