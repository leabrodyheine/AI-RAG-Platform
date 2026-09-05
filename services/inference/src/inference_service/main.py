from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from inference_service.backends import InferenceBackend, create_backend
from inference_service.config import Settings
from inference_service.dependencies import get_backend
from inference_service.routes.generate import router as generate_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    app.state.backend = create_backend(settings)
    try:
        yield
    finally:
        app.state.backend = None


app = FastAPI(title="Inference Service", version="0.1.0", lifespan=lifespan)
app.include_router(generate_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "inference", "status": "ok"}


@app.get("/ready", tags=["health"])
async def readiness(
    backend: Annotated[InferenceBackend, Depends(get_backend)],
) -> JSONResponse:
    return JSONResponse(
        content={"service": "inference", "status": "ready", "model": backend.model}
    )
