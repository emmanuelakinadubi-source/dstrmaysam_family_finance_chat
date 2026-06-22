"""File parsing and LLM-based event extraction service."""
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── File Parsing ──────────────────────────────────────────────────────────────

def parse_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(file_path: str) -> str:
    import docx
    doc = docx.Document(file_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_xlsx(file_path: str) -> str:
    import pandas as pd
    dfs = pd.read_excel(file_path, sheet_name=None)
    parts = []
    for sheet, df in dfs.items():
        parts.append(f"Sheet: {sheet}\n{df.to_string(index=False)}")
    return "\n\n".join(parts)


def parse_csv(file_path: str) -> str:
    import pandas as pd
    df = pd.read_csv(file_path)
    return df.to_string(index=False)


def extract_text(file_path: str, file_type: str) -> str:
    parsers = {
        "pdf": parse_pdf,
        "docx": parse_docx,
        "doc": parse_docx,
        "xlsx": parse_xlsx,
        "xls": parse_xlsx,
        "csv": parse_csv,
    }
    parser = parsers.get(file_type.lower())
    if not parser:
        raise ValueError(f"Unsupported file type: {file_type}")
    try:
        return parser(file_path)
    except Exception as e:
        logger.error("File parsing failed for %s: %s", file_path, e)
        raise


# ── LLM Extraction (delegates to agent) ──────────────────────────────────────

def extract_event_from_text(text: str) -> dict:
    """Extract structured event details from raw document text via the extraction agent."""
    from app.modules.agents.extraction_agent import run_extraction
    return run_extraction(text)


# ── ChromaDB Indexing ─────────────────────────────────────────────────────────

def index_event_document(text: str, event_id: str, filename: str) -> list[str]:
    """Chunk and embed document text into ChromaDB under collection 'event_documents'."""
    try:
        from app.modules.rag.pipeline import ingest_text
        return ingest_text(
            text=text,
            metadata={"event_id": event_id, "filename": filename, "source": "event_upload"},
            collection="event_documents",
        )
    except Exception as e:
        logger.warning("ChromaDB indexing skipped: %s", e)
        return []


# ── Vendor Recommendation ─────────────────────────────────────────────────────

def recommend_vendors_for_event(event, db) -> dict:
    """Match vendors against an event plan and return ranked recommendations."""
    from app.models.vendor import Vendor

    days = event.number_of_days or 1
    attendees = event.attendee_count or 1
    budget = event.budget or 0.0

    all_vendors = db.query(Vendor).filter(Vendor.is_active.is_(True)).all()

    matches = []
    for vendor in all_vendors:
        # Only include relevant vendor types
        if vendor.vendor_type == "Catering" and not event.food_required:
            continue
        if vendor.vendor_type in ("Hotel", "Conference") and not event.hosting_required:
            continue

        cost = vendor.price_per_person * attendees
        if vendor.vendor_type in ("Hotel", "Conference"):
            cost *= days

        remaining = round(budget - cost, 2)
        fit = round(max(0.0, 1.0 - abs(cost - budget) / budget), 3) if budget > 0 else 0.0
        city_match = (vendor.city.lower() == (event.city or "").lower())

        matches.append({
            "vendor_name": vendor.vendor_name,
            "vendor_type": vendor.vendor_type,
            "city": vendor.city,
            "price_per_person": vendor.price_per_person,
            "estimated_cost": round(cost, 2),
            "budget_remaining": remaining,
            "fit_score": fit,
            "city_match": city_match,
        })

    if not matches:
        return {"best_match": None, "cheapest_match": None, "closest_match": None, "all_matches": []}

    by_fit = sorted(matches, key=lambda x: -x["fit_score"])
    by_cost = sorted(matches, key=lambda x: x["estimated_cost"])
    by_city = [m for m in matches if m["city_match"]]

    for i, m in enumerate(by_fit, 1):
        m["rank"] = i

    return {
        "best_match": by_fit[0] if by_fit else None,
        "cheapest_match": by_cost[0] if by_cost else None,
        "closest_match": by_city[0] if by_city else None,
        "all_matches": by_fit,
    }
