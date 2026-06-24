import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.chat import router as chat_router
from app.routes.event import router as event_router
from app.routes.health import router as health_router
from app.routes.index import router as index_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.scheduler import shutdown_scheduler, start_scheduler

    # Create all tables if they don't exist (safe — never drops existing data)
    try:
        from app.core.database import engine
        from app.db.base import Base
        import app.models.budget       # noqa: F401
        import app.models.vendor       # noqa: F401
        import app.models.event        # noqa: F401
        import app.models.upload       # noqa: F401
        import app.models.chat         # noqa: F401
        import app.models.report       # noqa: F401
        import app.models.audit        # noqa: F401
        import app.models.event_draft  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified / created")
    except Exception as exc:
        logger.warning("Table creation skipped: %s", exc)

    # Seed vendors on startup (non-fatal if DB not available)
    try:
        from app.core.database import SessionLocal
        from app.modules.vendors.seeder import seed_vendors
        db = SessionLocal()
        seed_vendors(db)
        db.close()
    except Exception as exc:
        logger.warning("Vendor seeding skipped: %s", exc)

    start_scheduler()
    logger.info("Application startup complete")
    yield
    shutdown_scheduler()
    logger.info("Application shutdown complete")


app = FastAPI(title="Event Manager API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core event intelligence routes
app.include_router(health_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(index_router, prefix="/api")

# Extended platform modules (family, events, vendors, reports, analytics)
try:
    from fastapi import APIRouter
    from typing import Optional
    from pydantic import BaseModel as _BaseModel
    from app.modules.events.router import router as events_module_router
    from app.modules.family.router import router as family_router
    from app.modules.company.router import router as company_router
    from app.modules.vendors.router import router as vendors_router
    from app.modules.reports.router import router as reports_router
    from app.modules.analytics.router import router as analytics_router

    PREFIX = "/api/v1"
    app.include_router(events_module_router, prefix=PREFIX)
    app.include_router(family_router, prefix=PREFIX)
    app.include_router(company_router, prefix=PREFIX)
    app.include_router(vendors_router, prefix=PREFIX)
    app.include_router(reports_router, prefix=PREFIX)
    app.include_router(analytics_router, prefix=PREFIX)

    # Vendor AI endpoint
    _vendor_ai_router = APIRouter(prefix="/vendor-ai", tags=["Vendor AI"])

    class _VendorAIRequest(_BaseModel):
        city: str
        attendee_count: int
        budget: float
        number_of_days: int = 1
        food_required: bool = True
        hosting_required: bool = True

    @_vendor_ai_router.post("/recommend")
    def _vendor_ai_recommend(data: _VendorAIRequest):
        from app.modules.agents.vendor_agent import run_vendor_reasoning
        return {"recommendation": run_vendor_reasoning(
            city=data.city, attendee_count=data.attendee_count, budget=data.budget,
            number_of_days=data.number_of_days, food_required=data.food_required,
            hosting_required=data.hosting_required,
        )}

    app.include_router(_vendor_ai_router, prefix=PREFIX)
    logger.info("Extended platform modules loaded")
except ImportError as exc:
    logger.warning("Extended modules not available: %s", exc)
