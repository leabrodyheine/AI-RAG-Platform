from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from rag_observability import instrument_app

from api_gateway.clients.agent import AgentClient
from api_gateway.config import Settings, cors_allowed_origins_from_env
from api_gateway.routes.chat import router as chat_router
from api_gateway.routes.health import router as health_router
from api_gateway.schemas import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    agent_client = AgentClient.from_settings(Settings.from_env())
    app.state.agent_client = agent_client
    try:
        yield
    finally:
        await agent_client.aclose()


app = FastAPI(title="AI Production Evaluation API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_allowed_origins_from_env()),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.include_router(chat_router)
app.include_router(health_router)

# Structured logging, request/trace IDs, inbound + outbound HTTP spans, the
# http_server_* metrics, and GET /metrics.
instrument_app(app, "api-gateway")


@app.exception_handler(RequestValidationError)
async def handle_request_validation(
    request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    request_id = request.state.request_id
    error = ErrorResponse(
        code="validation_error",
        message="The chat request failed validation.",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error.model_dump(by_alias=True),
        headers={"X-Request-ID": request_id},
    )
