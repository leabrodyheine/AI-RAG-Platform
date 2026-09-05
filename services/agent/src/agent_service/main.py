from fastapi import FastAPI

from agent_service.routes.chat import router as chat_router

app = FastAPI(title="Agent Service", version="0.1.0")
app.include_router(chat_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "agent", "status": "ok"}
