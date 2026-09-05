from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse

from retrieval_service.config import Settings
from retrieval_service.database import DocumentStore
from retrieval_service.dependencies import get_document_store
from retrieval_service.routes.documents import router as documents_router
from retrieval_service.routes.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database_url = Settings.from_env().database_url
    document_store = await DocumentStore.connect(database_url) if database_url else None
    app.state.document_store = document_store
    try:
        yield
    finally:
        if document_store is not None:
            await document_store.close()


app = FastAPI(title="Retrieval Service", version="0.1.0", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(search_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "retrieval", "status": "ok"}


@app.get("/ready", tags=["health"])
async def readiness(
    document_store: Annotated[DocumentStore | None, Depends(get_document_store)],
) -> JSONResponse:
    if document_store is None:
        return JSONResponse(
            content={"service": "retrieval", "status": "ready", "storage": "memory"}
        )

    try:
        storage_ready = await document_store.is_ready()
    except Exception:
        storage_ready = False

    if not storage_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"service": "retrieval", "status": "not_ready", "storage": "postgres"},
        )
    return JSONResponse(
        content={"service": "retrieval", "status": "ready", "storage": "postgres"}
    )
