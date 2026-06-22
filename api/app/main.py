import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes.chat import router as chat_router
from app.routes.event import router as event_router
from app.routes.health import router as health_router
from app.routes.index import router as index_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import shutdown_scheduler, start_scheduler
    start_scheduler()
    logger.info("Application startup complete")
    yield
    shutdown_scheduler()
    logger.info("Application shutdown complete")


app = FastAPI(title="Event Intelligence Platform API", version="3.0.0", lifespan=lifespan)

app.include_router(health_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(index_router, prefix="/api")
