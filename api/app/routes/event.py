import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agent.event_agent import process_event_requirements
from app.core.database import get_db
from app.models.event_draft import EventDraft
from app.modules.events import repository as repo
from app.schemas.event import (
    EventRequirements,
    EventUploadResponse,
    RecommendationSummary,
    ScoreBreakdown,
    VenueCard,
)
from app.services.indexing_service import run_incremental_indexing
from app.tools.chromadb_storage import collection_count
from app.tools.doc_parser import parse_doc
from app.tools.event_storage import store_event_requirements
from app.tools.guardrails import check_prompt_injection, validate_event_requirements
from app.tools.pdf_parser import parse_pdf

router = APIRouter()
logger = logging.getLogger(__name__)

_ALLOWED_EXT = {".pdf", ".doc", ".docx"}


@router.post("/event/upload", response_model=EventUploadResponse)
async def upload_event(
    file: Optional[UploadFile] = File(default=None),
    text: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    if not file and not text:
        raise HTTPException(status_code=400, detail="Provide a file or text input.")

    if file:
        ext = _ext(file.filename)
        if ext not in _ALLOWED_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Allowed: PDF, DOC, DOCX.",
            )
        raw_bytes = await file.read()
        raw_text = parse_pdf(raw_bytes) if ext == ".pdf" else parse_doc(raw_bytes)
    else:
        raw_text = text

    if not raw_text or not raw_text.strip():
        raise HTTPException(status_code=400, detail="No readable text found in submission.")

    if check_prompt_injection(raw_text):
        raise HTTPException(status_code=400, detail="Submission contains disallowed content.")

    # Lazy-index venues on first request (non-fatal — skipped if credentials missing)
    try:
        _ensure_venues_indexed()
    except Exception as exc:
        logger.warning("Venue indexing skipped (non-fatal): %s", exc)

    # Run single agent: extract + recommend
    try:
        agent_result = process_event_requirements(raw_text)
    except Exception as exc:
        logger.error("Agent failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"AI agent error — check that AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT are set in .env. Details: {exc}",
        )

    # Build EventRequirements from agent output
    req_data = agent_result.get("event_requirements") or {}
    requirements = EventRequirements(
        event_date=req_data.get("event_date", ""),
        event_time=req_data.get("event_time", ""),
        city=req_data.get("city", ""),
        min_budget=float(req_data.get("min_budget", 0) or 0),
        max_budget=float(req_data.get("max_budget", 0) or 0),
        attendees=int(req_data.get("attendees", 0) or 0),
        additional_requirements=req_data.get("additional_requirements", []) or [],
    )

    # Output guardrail
    errors = validate_event_requirements(requirements)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    # Persist event to PostgreSQL (non-fatal)
    event_id = None
    try:
        city = req_data.get("city", "")
        date = req_data.get("event_date", "")
        db_payload = {
            "event_name": f"Event – {city} {date}".strip(" –"),
            "city": city,
            "event_date": date,
            "event_time": req_data.get("event_time"),
            "attendee_count": int(req_data.get("attendees", 0) or 0),
            "budget": float(req_data.get("max_budget") or req_data.get("min_budget") or 0),
        }
        event = repo.create_event(db, db_payload)
        event_id = str(event.id)
    except Exception as exc:
        logger.warning("DB persistence failed (non-fatal): %s", exc)

    # Index the event requirements for Chat-based querying
    event_collection = "event_management"
    if req_data:
        try:
            event_collection = store_event_requirements(raw_text, req_data)
        except Exception as exc:
            logger.warning("Event indexing failed (non-fatal): %s", exc)

    # Build VenueCard objects
    venue_cards = []
    for v in agent_result.get("recommended_venues", []):
        breakdown_data = v.get("score_breakdown", {})
        breakdown = ScoreBreakdown(**breakdown_data) if breakdown_data else None
        try:
            venue_cards.append(VenueCard(
                venue_id=v.get("venue_id", ""),
                venue_name=v.get("venue_name", "Unknown"),
                venue_image=v.get("venue_image", ""),
                city=v.get("city", ""),
                postcode=v.get("postcode", ""),
                capacity=v.get("capacity", "Unknown"),
                budget_compatibility=v.get("budget_compatibility", "—"),
                venue_description=v.get("venue_description", "")[:350],
                venue_features=v.get("venue_features", []),
                event_types=v.get("event_types", []),
                venue_url=v.get("venue_url", ""),
                match_score=float(v.get("match_score", 0)),
                score_breakdown=breakdown,
                recommendation_reason=v.get("recommendation_reason", ""),
                is_fallback=bool(v.get("is_fallback", False)),
                parking=_safe_bool(v.get("parking")),
                wifi=_safe_bool(v.get("wifi")),
                av_equipment=_safe_bool(v.get("av_equipment")),
                hybrid_events=_safe_bool(v.get("hybrid_events")),
                catering=_safe_bool(v.get("catering")),
                wheelchair_access=_safe_bool(v.get("wheelchair_access")),
                outdoor_space=_safe_bool(v.get("outdoor_space")),
                nearest_train=v.get("nearest_train", ""),
                response_rate=v.get("response_rate", ""),
                response_time=v.get("response_time", ""),
                sustainability=v.get("sustainability", ""),
            ))
        except Exception as exc:
            logger.warning("Could not build VenueCard for %s: %s", v.get("venue_name"), exc)

    # Build summary
    summary_data = agent_result.get("summary") or {}
    summary = RecommendationSummary(
        total_venues=summary_data.get("total_venues", len(venue_cards)),
        best_venue=summary_data.get("best_venue", venue_cards[0].venue_name if venue_cards else "None"),
        budget_analysis=summary_data.get("budget_analysis", "N/A"),
        capacity_analysis=summary_data.get("capacity_analysis", "N/A"),
        key_recommendations=summary_data.get("key_recommendations", []),
    )

    if not venue_cards:
        summary = _empty_summary()

    response = EventUploadResponse(
        event_id=event_id,
        event_requirements=requirements,
        recommended_venues=venue_cards,
        summary=summary,
        agent_response=agent_result.get("agent_response", ""),
        event_collection=event_collection,
    )

    # Persist draft to DB so the user can reload without re-uploading
    try:
        draft = EventDraft(
            filename=file.filename if file else "Manual text input",
            event_name=f"Event – {req_data.get('city', '')} {req_data.get('event_date', '')}".strip(" –"),
            city=req_data.get("city", ""),
            postcode=req_data.get("postcode", ""),
            event_date=req_data.get("event_date", ""),
            attendees=int(req_data.get("attendees", 0) or 0),
            max_budget=str(req_data.get("max_budget") or req_data.get("min_budget") or ""),
            event_collection=event_collection,
            event_id=event_id,
            requirements_json=requirements.model_dump_json(),
            venues_json=json.dumps([v.model_dump() for v in venue_cards]),
            summary_json=summary.model_dump_json(),
            agent_response=agent_result.get("agent_response", ""),
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        response.event_id = response.event_id or str(draft.id)
        logger.info("Event draft persisted: %s", draft.id)
    except Exception as exc:
        logger.warning("Draft persistence failed (non-fatal): %s", exc)

    return response


@router.get("/event/drafts")
async def list_event_drafts(db: Session = Depends(get_db)):
    """Return all saved event drafts, newest first."""
    drafts = db.query(EventDraft).order_by(EventDraft.created_at.desc()).all()
    return [
        {
            "draft_id":        str(d.id),
            "filename":        d.filename,
            "event_name":      d.event_name,
            "city":            d.city,
            "postcode":        d.postcode,
            "event_date":      d.event_date,
            "attendees":       d.attendees,
            "max_budget":      d.max_budget,
            "event_collection": d.event_collection,
            "event_id":        d.event_id,
            "created_at":      d.created_at.isoformat() if d.created_at else None,
        }
        for d in drafts
    ]


@router.get("/event/drafts/{draft_id}")
async def get_event_draft(draft_id: str, db: Session = Depends(get_db)):
    """Load a saved draft — returns the full EventUploadResponse payload."""
    draft = db.query(EventDraft).filter(EventDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    try:
        requirements = json.loads(draft.requirements_json) if draft.requirements_json else {}
        venues       = json.loads(draft.venues_json)       if draft.venues_json       else []
        summary      = json.loads(draft.summary_json)      if draft.summary_json      else {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft data corrupt: {exc}")
    return {
        "draft_id":         str(draft.id),
        "filename":         draft.filename,
        "event_id":         draft.event_id,
        "event_collection": draft.event_collection,
        "event_requirements": requirements,
        "recommended_venues": venues,
        "summary":          summary,
        "agent_response":   draft.agent_response,
    }


@router.delete("/event/drafts/{draft_id}", status_code=204)
async def delete_event_draft(draft_id: str, db: Session = Depends(get_db)):
    """Permanently remove a saved draft."""
    draft = db.query(EventDraft).filter(EventDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found.")
    db.delete(draft)
    db.commit()
    return None


@router.get("/event/recommendations")
async def recommendations_status():
    return {"status": "ok", "indexed_chunks": collection_count()}


@router.post("/event/index-venues")
async def index_venues(force: bool = False):
    from app.services.indexing_service import run_full_reindex
    if force:
        result = run_full_reindex()
    else:
        result = run_incremental_indexing()
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("error", "Indexing failed"))
    return result


def _ensure_venues_indexed() -> None:
    if collection_count() == 0:
        logger.info("ChromaDB empty — running initial incremental indexing")
        run_incremental_indexing()


def _ext(filename: str) -> str:
    _, ext = os.path.splitext((filename or "").lower())
    return ext


def _safe_bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "yes", "1")
    return None


def _empty_summary() -> RecommendationSummary:
    return RecommendationSummary(
        total_venues=0,
        best_venue="No venues found",
        budget_analysis="No venues matched your criteria",
        capacity_analysis="No capacity data available",
        key_recommendations=["Try broadening your search or adjusting budget/location"],
    )
