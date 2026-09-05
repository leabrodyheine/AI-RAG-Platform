from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api_gateway.clients.agent import AgentClient
from api_gateway.config import Settings
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
app.include_router(chat_router)
app.include_router(health_router)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    caller_request_id = request.headers.get("X-Request-ID")
    request_id = (
        caller_request_id
        if caller_request_id and len(caller_request_id) <= 128
        else str(uuid4())
    )
    request.state.request_id = request_id

    response = await call_next(request)
    if "X-Request-ID" not in response.headers:
        response.headers["X-Request-ID"] = request_id
    return response


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
