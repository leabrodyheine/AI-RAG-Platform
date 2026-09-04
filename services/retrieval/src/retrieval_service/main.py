from fastapi import FastAPI

app = FastAPI(title="Retrieval Service", version="0.1.0")


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"service": "retrieval", "status": "ok"}
