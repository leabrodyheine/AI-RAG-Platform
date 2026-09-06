import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from rag_observability import instrument_app

from retrieval_service.cache import RetrievalCache
from retrieval_service.config import Settings
from retrieval_service.database import DocumentStore
from retrieval_service.dependencies import get_document_store
from retrieval_service.embeddings import create_embedding_provider
from retrieval_service.routes.documents import router as documents_router
from retrieval_service.routes.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    if settings.database_url:
        embedding_provider = await asyncio.to_thread(
            create_embedding_provider,
            settings.embedding_provider,
            model_name=settings.embedding_model,
            model_version=settings.embedding_model_version,
            cache_dir=settings.embedding_cache_dir,
        )
        document_store = await DocumentStore.connect(
            settings.database_url,
            embedding_provider,
        )
    else:
        document_store = None
    retrieval_cache = (
        RetrievalCache.from_url(settings.redis_url, settings.cache_ttl_seconds)
        if document_store is not None and settings.redis_url is not None
        else None
    )
    app.state.document_store = document_store
    app.state.retrieval_cache = retrieval_cache
    try:
        yield
    finally:
        if retrieval_cache is not None:
            await retrieval_cache.close()
        if document_store is not None:
            await document_store.close()
        app.state.retrieval_cache = None
        app.state.document_store = None


app = FastAPI(title="Retrieval Service", version="0.1.0", lifespan=lifespan)
app.include_router(documents_router)
app.include_router(search_router)
instrument_app(app, "retrieval")


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
