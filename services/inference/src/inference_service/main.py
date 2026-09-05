from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from inference_service.backends import InferenceBackend, create_backend
from inference_service.config import Settings
from inference_service.dependencies import get_backend
from inference_service.routes.generate import router as generate_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    backend = create_backend(settings)
    app.state.backend = backend
    try:
        yield
    finally:
        await backend.aclose()
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
    try:
        model_ready = await backend.ready()
    except Exception:
        model_ready = False

    body = {
        "service": "inference",
        "status": "ready" if model_ready else "not_ready",
        "backend": backend.name,
        "model": backend.model,
    }
    if not model_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body)
    return JSONResponse(content=body)
