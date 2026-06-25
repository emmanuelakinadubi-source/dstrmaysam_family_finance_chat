import uuid
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.modules.events import repository as repo
from app.modules.events.service import recommend_vendors_for_event
from app.modules.events.schemas import EventPlanOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])


@router.get("/", response_model=List[EventPlanOut])
def list_events(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return repo.list_events(db, skip, limit)


@router.get("/{event_id}", response_model=EventPlanOut)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)):
    event = repo.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/{event_id}/recommendations")
def get_vendor_recommendations(event_id: uuid.UUID, db: Session = Depends(get_db)):
    event = repo.get_event(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    recs = recommend_vendors_for_event(event, db)
    return {
        "event_id": str(event.id),
        "event_name": event.event_name,
        "budget": event.budget,
        **recs,
    }


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)):
    from app.models.event import EventPlan
    from sqlalchemy import func
    total_events = db.query(func.count(EventPlan.id)).filter(EventPlan.deleted_at.is_(None)).scalar()
    total_budget = db.query(func.sum(EventPlan.budget)).filter(EventPlan.deleted_at.is_(None)).scalar() or 0.0
    recent = repo.list_events(db, limit=5)
    return {
        "total_events": total_events,
        "total_budget": round(total_budget, 2),
        "recent_events": [{"id": str(e.id), "event_name": e.event_name, "city": e.city, "budget": e.budget} for e in recent],
    }
