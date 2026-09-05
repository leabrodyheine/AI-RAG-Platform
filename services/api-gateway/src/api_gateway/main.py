from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api_gateway.clients.agent import AgentClient
from api_gateway.config import Settings
from api_gateway.routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    agent_client = AgentClient.from_settings(Settings.from_env())
    app.state.agent_client = agent_client
    try:
        yield
    finally:
        await agent_client.aclose()


app = FastAPI(title="AI Production Evaluation API", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
