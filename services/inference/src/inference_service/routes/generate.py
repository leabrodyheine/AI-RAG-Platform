from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse

from inference_service.backends import (
    InferenceBackend,
    InferenceBackendError,
    InferenceBackendTimeoutError,
)
from inference_service.dependencies import get_backend
from inference_service.schemas import GenerationRequest, GenerationResponse, TokenUsage

router = APIRouter(tags=["inference"])


@router.post(
    "/generate",
    operation_id="generateText",
    summary="Generate text from a completed prompt",
    response_model=GenerationResponse,
)
async def generate(
    payload: GenerationRequest,
    response: Response,
    backend: Annotated[InferenceBackend, Depends(get_backend)],
    caller_request_id: Annotated[
        str | None,
        Header(alias="X-Request-ID", min_length=1, max_length=128),
    ] = None,
) -> GenerationResponse | JSONResponse:
    request_id = caller_request_id or str(uuid4())

    try:
        result = await backend.generate(
            payload.prompt,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
    except InferenceBackendTimeoutError:
        return _error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "The inference backend did not respond in time.",
            request_id,
        )
    except InferenceBackendError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The inference backend is unavailable.",
            request_id,
        )

    response.headers["X-Request-ID"] = request_id
    return GenerationResponse(
        content=result.content,
        model=backend.model,
        usage=TokenUsage(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
        ),
    )


def _error_response(status_code: int, detail: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers={"X-Request-ID": request_id},
    )
