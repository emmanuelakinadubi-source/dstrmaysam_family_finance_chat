import os
import uuid
import logging
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.modules.events import repository as repo
from app.modules.events.service import extract_text, extract_event_from_text, index_event_document, recommend_vendors_for_event
from app.modules.events.schemas import EventPlanOut, VendorRecommendationsOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["Events"])

ALLOWED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "csv"}


def _save_file(upload: UploadFile) -> tuple[str, str]:
    """Save upload to disk, return (file_path, extension)."""
    ext = Path(upload.filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4()}_{upload.filename}"
    file_path = str(upload_dir / unique_name)
    with open(file_path, "wb") as f:
        f.write(upload.file.read())
    return file_path, ext


@router.post("/upload", status_code=status.HTTP_201_CREATED)
def upload_event_plan(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Full pipeline:
    1. Save file → 2. Parse text → 3. Extract event via LLM agent
    4. Store in PostgreSQL → 5. Index in ChromaDB → return extracted event
    """
    file_path, ext = _save_file(file)

    try:
        text = extract_text(file_path, ext)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse file: {e}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="File appears to be empty or unreadable")

    try:
        extracted = extract_event_from_text(text)
    except Exception as e:
        logger.warning("LLM extraction failed, storing raw: %s", e)
        extracted = {"event_name": file.filename, "extraction_error": str(e)}

    event = repo.create_event(db, extracted)

    repo.save_uploaded_file(db, event.id, file.filename, file_path, ext, text[:5000])

    index_event_document(text, str(event.id), file.filename)

    return {
        "event_id": str(event.id),
        "extracted": extracted,
        "file": file.filename,
        "status": "indexed",
    }


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
