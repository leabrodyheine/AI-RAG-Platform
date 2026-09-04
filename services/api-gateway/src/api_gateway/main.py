from fastapi import FastAPI

from api_gateway.routes.health import router as health_router

app = FastAPI(title="AI Production Evaluation API", version="0.1.0")
app.include_router(health_router)
