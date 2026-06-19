import uuid
from typing import List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.event import EventPlan
from app.models.upload import UploadedFile


def create_event(db: Session, extracted: dict) -> EventPlan:
    event = EventPlan(
        event_name=extracted.get("event_name", "Unnamed Event"),
        city=extracted.get("city"),
        event_date=extracted.get("event_date"),
        event_time=extracted.get("event_time"),
        attendee_count=extracted.get("attendee_count"),
        number_of_days=extracted.get("number_of_days", 1),
        food_required=extracted.get("food_required", False),
        hosting_required=extracted.get("hosting_required", False),
        budget=extracted.get("budget"),
        extracted_data=extracted,
        status="active",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def save_uploaded_file(db: Session, event_id: uuid.UUID, filename: str,
                       file_path: str, file_type: str, parsed_content: str) -> UploadedFile:
    record = UploadedFile(
        filename=filename,
        original_name=filename,
        file_type=file_type,
        file_path=file_path,
        parsed_content=parsed_content,
        module="company",
        entity_id=event_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_events(db: Session, skip: int = 0, limit: int = 50) -> List[EventPlan]:
    return (
        db.query(EventPlan)
        .filter(EventPlan.deleted_at.is_(None))
        .order_by(EventPlan.created_at.desc())
        .offset(skip).limit(limit).all()
    )


def get_event(db: Session, event_id: uuid.UUID) -> Optional[EventPlan]:
    return db.query(EventPlan).filter(
        EventPlan.id == event_id, EventPlan.deleted_at.is_(None)
    ).first()


def get_events_with_files(db: Session) -> list:
    events = list_events(db)
    result = []
    for e in events:
        files = db.query(UploadedFile).filter(UploadedFile.entity_id == e.id).all()
        result.append({"event": e, "files": files})
    return result
