from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api_gateway.clients.agent import AgentClient, AgentClientError, AgentTimeoutError
from api_gateway.dependencies import get_agent_client
from api_gateway.schemas import ChatRequest, ChatResponse, ErrorCode, ErrorResponse

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    operation_id="createChatAnswer",
    summary="Answer an investigation question",
    description=(
        "Forwards a validated question through the agent workflow and returns its "
        "answer, supporting evidence, and timing trace."
    ),
    response_model=ChatResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
        status.HTTP_504_GATEWAY_TIMEOUT: {"model": ErrorResponse},
    },
)
async def create_chat_answer(
    payload: ChatRequest,
    request: Request,
    agent_client: Annotated[AgentClient, Depends(get_agent_client)],
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
) -> ChatResponse | JSONResponse:
    request_id = caller_request_id or request.state.request_id

    try:
        result = await agent_client.answer(payload.question, request_id=request_id)
        ChatResponse.model_validate(result.payload)
    except AgentTimeoutError:
        return _error_response(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="agent_timeout",
            message="The agent service did not respond in time.",
            request_id=request_id,
        )
    except (AgentClientError, ValidationError):
        return _error_response(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_unavailable",
            message="The agent service is temporarily unavailable.",
            request_id=request_id,
        )

    # The agent payload is already validated above and already contract-shaped
    # (camelCase, no extra keys). Forward its bytes rather than rebuilding a model
    # for FastAPI to validate and serialize a second time.
    return JSONResponse(
        content=result.payload,
        headers={"X-Request-ID": result.request_id},
    )


def _error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    request_id: str,
) -> JSONResponse:
    error = ErrorResponse(
        code=code,
        message=message,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=error.model_dump(by_alias=True),
        headers={"X-Request-ID": request_id},
    )
