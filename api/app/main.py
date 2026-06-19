import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.health import router as health_router
from app.modules.events.router import router as events_router
from app.modules.family.router import router as family_router
from app.modules.company.router import router as company_router
from app.modules.vendors.router import router as vendors_router
from app.modules.chat.router import router as chat_router
from app.modules.reports.router import router as reports_router
from app.modules.analytics.router import router as analytics_router
from app.core.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)

# ── Event Chat endpoint (uses the event RAG agent) ────────────────────────────
from fastapi import APIRouter, Depends
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db

event_chat_router = APIRouter(prefix="/event-chat", tags=["Event Chat"])


class EventChatRequest(BaseModel):
    question: str
    event_id: Optional[str] = None
    evaluate: bool = False


@event_chat_router.post("/")
def event_chat(data: EventChatRequest, db: Session = Depends(get_db)):
    from app.modules.agents.chat_agent import run_event_chat
    return run_event_chat(
        question=data.question,
        event_id=data.event_id,
        evaluate=data.evaluate,
    )


# ── Vendor AI reasoning endpoint ───────────────────────────────────────────────
vendor_ai_router = APIRouter(prefix="/vendor-ai", tags=["Vendor AI"])


class VendorAIRequest(BaseModel):
    city: str
    attendee_count: int
    budget: float
    number_of_days: int = 1
    food_required: bool = True
    hosting_required: bool = True


@vendor_ai_router.post("/recommend")
def vendor_ai_recommend(data: VendorAIRequest):
    from app.modules.agents.vendor_agent import run_vendor_reasoning
    narrative = run_vendor_reasoning(
        city=data.city,
        attendee_count=data.attendee_count,
        budget=data.budget,
        number_of_days=data.number_of_days,
        food_required=data.food_required,
        hosting_required=data.hosting_required,
    )
    return {"recommendation": narrative}


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Seed vendor table on first start
    try:
        from app.core.database import SessionLocal
        from app.modules.vendors.seeder import seed_vendors
        db = SessionLocal()
        seed_vendors(db)
        db.close()
    except Exception as e:
        logger.warning("Vendor seeding skipped: %s", e)

    start_scheduler()
    yield
    stop_scheduler()


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Family Finance & Company Event Planning AI Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"

app.include_router(health_router, prefix=PREFIX)
app.include_router(events_router, prefix=PREFIX)
app.include_router(event_chat_router, prefix=PREFIX)
app.include_router(vendor_ai_router, prefix=PREFIX)
app.include_router(family_router, prefix=PREFIX)
app.include_router(company_router, prefix=PREFIX)
app.include_router(vendors_router, prefix=PREFIX)
app.include_router(chat_router, prefix=PREFIX)
app.include_router(reports_router, prefix=PREFIX)
app.include_router(analytics_router, prefix=PREFIX)
