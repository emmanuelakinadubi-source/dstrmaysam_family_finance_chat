"""Seed the vendors table with MVP sample data on first startup."""
import logging
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

SEED_VENDORS = [
    # ── Catering ──────────────────────────────────────────────────────────────
    {"vendor_name": "Vendor A", "vendor_type": "Catering", "city": "London", "price_per_person": 15.0,
     "description": "Full-service catering for corporate events"},
    {"vendor_name": "Vendor B", "vendor_type": "Catering", "city": "Manchester", "price_per_person": 12.0,
     "description": "Budget-friendly catering, northern England"},
    {"vendor_name": "Prime Plates", "vendor_type": "Catering", "city": "London", "price_per_person": 22.0,
     "description": "Premium corporate catering with bespoke menus"},
    {"vendor_name": "Northern Bites", "vendor_type": "Catering", "city": "Birmingham", "price_per_person": 10.0,
     "description": "Affordable catering for large groups"},
    {"vendor_name": "Edinburgh Eats", "vendor_type": "Catering", "city": "Edinburgh", "price_per_person": 14.0,
     "description": "Scottish corporate catering specialists"},
    # ── Hotels ────────────────────────────────────────────────────────────────
    {"vendor_name": "Vendor C", "vendor_type": "Hotel", "city": "London", "price_per_person": 80.0,
     "description": "Central London hotel with conference facilities"},
    {"vendor_name": "Vendor D", "vendor_type": "Hotel", "city": "Birmingham", "price_per_person": 65.0,
     "description": "Business hotel in Birmingham city centre"},
    {"vendor_name": "Manchester Grand", "vendor_type": "Hotel", "city": "Manchester", "price_per_person": 70.0,
     "description": "4-star hotel with dedicated event spaces"},
    {"vendor_name": "Capital Stay", "vendor_type": "Hotel", "city": "London", "price_per_person": 95.0,
     "description": "Luxury hotel near financial district"},
    {"vendor_name": "Northern Heights", "vendor_type": "Hotel", "city": "Leeds", "price_per_person": 55.0,
     "description": "Modern hotel with flexible conference rooms"},
    # ── Conference Centres ────────────────────────────────────────────────────
    {"vendor_name": "London Conference Hub", "vendor_type": "Conference", "city": "London", "price_per_person": 45.0,
     "description": "Dedicated conference centre, state-of-the-art AV"},
    {"vendor_name": "Midlands Event Centre", "vendor_type": "Conference", "city": "Birmingham", "price_per_person": 35.0,
     "description": "Large conference centre, up to 500 delegates"},
]


def seed_vendors(db: Session) -> int:
    from app.models.vendor import Vendor

    existing = db.query(Vendor).count()
    if existing > 0:
        logger.info("Vendors already seeded (%d records) — skipping", existing)
        return 0

    for v in SEED_VENDORS:
        db.add(Vendor(**v, currency="GBP"))

    db.commit()
    logger.info("Seeded %d vendors into the database", len(SEED_VENDORS))
    return len(SEED_VENDORS)
