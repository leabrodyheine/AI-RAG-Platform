from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from rag_observability import instrument_app

from agent_service.clients.inference import InferenceClient
from agent_service.clients.retrieval import RetrievalClient
from agent_service.config import Settings
from agent_service.routes.chat import router as chat_router
from agent_service.workflow import WorkflowConfig


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    retrieval_client = RetrievalClient.from_settings(settings)
    inference_client = InferenceClient.from_settings(settings)
    app.state.retrieval_client = retrieval_client
    app.state.inference_client = inference_client
    app.state.workflow_config = WorkflowConfig(
        min_relevance=settings.workflow_min_relevance,
        min_results=settings.workflow_min_results,
        max_steps=settings.workflow_max_steps,
    )
    try:
        yield
    finally:
        await retrieval_client.aclose()
        await inference_client.aclose()


app = FastAPI(title="Agent Service", version="0.1.0", lifespan=lifespan)
app.include_router(chat_router)
instrument_app(app, "agent")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "agent", "status": "ok"}
