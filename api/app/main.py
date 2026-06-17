from fastapi import FastAPI
from app.routes.health import router as health_router
from app.routes.budget import router as budget_router

app = FastAPI(title="Family Finance API", version="1.0.0")

app.include_router(health_router, prefix="/api")
app.include_router(budget_router, prefix="/api")
