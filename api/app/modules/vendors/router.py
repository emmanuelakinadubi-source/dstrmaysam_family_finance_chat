from typing import List, Optional
from fastapi import APIRouter, Depends, BackgroundTasks
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
