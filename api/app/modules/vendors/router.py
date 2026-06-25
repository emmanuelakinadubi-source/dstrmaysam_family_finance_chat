from typing import List, Optional
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.vendor import VendorPrice
from app.modules.vendors.schemas import VendorPriceOut, VendorMatchRequest
from app.modules.vendors.crawler import run_crawl

router = APIRouter(prefix="/vendors", tags=["Vendors"])


@router.get("/list")
def list_vendors(
    city: Optional[str] = None,
    vendor_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """List simple Vendor table records (seeded MVP data)."""
    from app.models.vendor import Vendor
    q = db.query(Vendor).filter(Vendor.is_active.is_(True))
    if city:
        q = q.filter(Vendor.city.ilike(f"%{city}%"))
    if vendor_type:
        q = q.filter(Vendor.vendor_type.ilike(f"%{vendor_type}%"))
    vendors = q.order_by(Vendor.city, Vendor.price_per_person).all()
    return [
        {
            "id": str(v.id),
            "vendor_name": v.vendor_name,
            "vendor_type": v.vendor_type,
            "city": v.city,
            "price_per_person": v.price_per_person,
            "currency": v.currency,
            "description": v.description,
        }
        for v in vendors
    ]


@router.get("/prices", response_model=List[VendorPriceOut])
def list_prices(
    vendor_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(VendorPrice)
    if vendor_type:
        q = q.filter(VendorPrice.vendor_type == vendor_type)
    if category:
        q = q.filter(VendorPrice.category == category)
    return q.order_by(VendorPrice.price.asc()).limit(limit).all()


@router.get("/compare")
def compare_vendors(vendors: str, category: Optional[str] = None, db: Session = Depends(get_db)):
    names = [v.strip() for v in vendors.split(",")]
    q = db.query(VendorPrice).filter(VendorPrice.vendor_name.in_(names))
    if category:
        q = q.filter(VendorPrice.category == category)
    results = q.order_by(VendorPrice.vendor_name, VendorPrice.price).all()
    return [VendorPriceOut.model_validate(r) for r in results]


@router.post("/match")
def match_vendors(data: VendorMatchRequest, db: Session = Depends(get_db)):
    vendors = (
        db.query(VendorPrice)
        .filter(VendorPrice.vendor_type == data.vendor_type)
        .filter(VendorPrice.price <= data.budget / max(data.attendee_count, 1))
        .order_by(VendorPrice.price.asc())
        .limit(10)
        .all()
    )
    matches = []
    for rank, v in enumerate(vendors, 1):
        per_head = v.price
        total = per_head * data.attendee_count
        fit_score = round(max(0, 1 - (total / data.budget)), 2) if data.budget > 0 else 0
        matches.append({
            "vendor_name": v.vendor_name,
            "vendor_type": v.vendor_type,
            "per_head_cost": per_head,
            "estimated_total": total,
            "fit_score": fit_score,
            "rank": rank,
        })
    return matches


@router.post("/crawl")
def trigger_crawl(background_tasks: BackgroundTasks, foreground: bool = False):
    """
    Trigger a vendor + hotel scrape.
    - foreground=false (default): runs in background, returns immediately.
    - foreground=true: blocks until complete and returns full result summary.
    """
    if foreground:
        return run_crawl()
    background_tasks.add_task(run_crawl)
    return {"message": "Vendor crawl started in background — check logs for progress"}


@router.get("/crawl/schedule")
def crawl_schedule():
    """Return next scheduled run times for all background jobs."""
    from app.services.scheduler import get_next_run_time
    return {
        "daily_venue_indexing": get_next_run_time("daily_venue_indexing"),
        "weekly_vendor_crawl": get_next_run_time("weekly_vendor_crawl"),
    }


# ── Smart event-aware scrape endpoint ─────────────────────────────────────────

from pydantic import BaseModel as _BaseModel  # noqa: E402

class _EventScrapeRequest(_BaseModel):
    postcode: str
    city: str = ""
    attendees: int = 0
    total_budget: float = 0.0
    catering_budget: float = 0.0
    hotel_budget: float = 0.0
    radius_km: float = 5.0
    food_required: bool = True
    hotel_required: bool = True
    food_categories: List[str] = []
    event_id: Optional[str] = None


@router.post("/scrape-for-event")
def scrape_for_event(data: _EventScrapeRequest, background_tasks: BackgroundTasks):
    """
    Event-aware vendor scrape + RAG index pipeline.

    1. Resolves postcode → coordinates (postcodes.io)
    2. Scrapes nearby caterers + hotels via OSM Overpass (+ optional feedr.co)
    3. Applies guardrails: radius, budget, dietary requirements
    4. Embeds results → ChromaDB vendor_intel collection
    5. Returns summary — chat agent can now answer vendor questions for this event
    """
    from app.modules.vendors.smart_scraper import EventScraperConfig, run_event_scrape
    from app.modules.vendors.vendor_pipeline import run_pipeline
    from app.modules.vendors.vendor_indexer import index_vendors

    config = EventScraperConfig(
        postcode=data.postcode.strip(),
        city=data.city,
        attendees=data.attendees,
        total_budget=data.total_budget,
        catering_budget=data.catering_budget,
        hotel_budget=data.hotel_budget,
        radius_km=data.radius_km,
        food_required=data.food_required,
        hotel_required=data.hotel_required,
        food_categories=data.food_categories,
        event_id=data.event_id,
    )

    try:
        raw = run_event_scrape(config)
        cleaned = run_pipeline(raw, config)
        index_result = index_vendors(cleaned, event_id=data.event_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scrape failed: {exc}")

    caterers = [v for v in cleaned if v.vendor_type == "catering"]
    hotels   = [v for v in cleaned if v.vendor_type == "hotel"]

    # If nothing found, suggest nearby towns
    nearby_towns = []
    if len(cleaned) == 0:
        from app.modules.vendors.smart_scraper import get_nearby_towns
        nearby_towns = get_nearby_towns(data.postcode)

    return {
        "status": "ok",
        "postcode": data.postcode,
        "radius_km": data.radius_km,
        "raw_count": len(raw),
        "filtered_count": len(cleaned),
        "caterers_found": len(caterers),
        "hotels_found": len(hotels),
        "indexed": index_result.get("indexed", 0),
        "collection": index_result.get("collection"),
        "nearby_towns": nearby_towns,
        "top_caterers": [
            {
                "name": v.name,
                "distance_km": v.distance_km,
                "delivery_available": v.delivery_available,
                "price_per_head": v.price_per_head,
                "specializations": v.specializations,
                "cuisine": v.cuisine,
                "address": v.address,
                "phone": v.phone,
                "website": v.website,
                "source": v.source,
            }
            for v in caterers[:15]
        ],
        "top_hotels": [
            {
                "name": v.name,
                "distance_km": v.distance_km,
                "delivery_available": v.delivery_available,
                "price_per_head": v.price_per_head,
                "address": v.address,
                "phone": v.phone,
                "website": v.website,
                "source": v.source,
            }
            for v in hotels[:15]
        ],
    }


@router.get("/intel/count")
def vendor_intel_count():
    """Number of scraped vendor documents currently in ChromaDB."""
    from app.modules.vendors.vendor_indexer import vendor_intel_count
    return {"vendor_intel_documents": vendor_intel_count()}
