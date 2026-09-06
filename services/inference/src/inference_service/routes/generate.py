from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import JSONResponse
from rag_observability import current_request_id, get_tracer, record_generation

from inference_service.backends import (
    InferenceBackend,
    InferenceBackendError,
    InferenceBackendTimeoutError,
)
from inference_service.dependencies import get_backend
from inference_service.schemas import GenerationRequest, GenerationResponse, TokenUsage

router = APIRouter(tags=["inference"])
_tracer = get_tracer("inference.generate")
_SERVICE = "inference"


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
    request_id = caller_request_id or current_request_id() or str(uuid4())

    with _tracer.start_as_current_span("inference.generate") as span:
        span.set_attribute("inference.backend", backend.name)
        span.set_attribute("inference.model", backend.model)
        span.set_attribute("inference.max_tokens", payload.max_tokens)

        started = perf_counter()
        try:
            result = await backend.generate(
                payload.prompt,
                max_tokens=payload.max_tokens,
                temperature=payload.temperature,
            )
        except InferenceBackendTimeoutError:
            span.set_attribute("inference.outcome", "timeout")
            return _error_response(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "The inference backend did not respond in time.",
                request_id,
            )
        except InferenceBackendError:
            span.set_attribute("inference.outcome", "unavailable")
            return _error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "The inference backend is unavailable.",
                request_id,
            )

        duration_seconds = perf_counter() - started
        span.set_attribute("inference.prompt_tokens", result.prompt_tokens)
        span.set_attribute("inference.completion_tokens", result.completion_tokens)
        record_generation(
            _SERVICE,
            backend.name,
            backend.model,
            duration_seconds=duration_seconds,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
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
