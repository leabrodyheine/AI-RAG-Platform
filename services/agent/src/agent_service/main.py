from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agent_service.clients.retrieval import RetrievalClient
from agent_service.config import Settings
from agent_service.routes.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    retrieval_client = RetrievalClient.from_settings(Settings.from_env())
    app.state.retrieval_client = retrieval_client
    try:
        yield
    finally:
        await retrieval_client.aclose()


app = FastAPI(title="Agent Service", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "agent", "status": "ok"}
