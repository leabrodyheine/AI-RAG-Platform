from fastapi import FastAPI

from retrieval_service.routes.search import router as search_router

app = FastAPI(title="Retrieval Service", version="0.1.0")
app.include_router(search_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "retrieval", "status": "ok"}
