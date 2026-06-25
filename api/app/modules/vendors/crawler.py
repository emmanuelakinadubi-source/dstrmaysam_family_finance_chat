"""
Vendor and hotel scraper using the OpenStreetMap Overpass API.

Runs on a weekly schedule (Sundays 02:00 UTC via scheduler.py).
Can also be triggered manually via POST /api/v1/vendors/crawl.

Data flow:
  Overpass API (hotels + caterers per UK city)
    → upsert into Vendor table (name, type, city, price_per_person)
    → upsert into VendorPrice table (catering package catalog)
"""
import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# UK cities to scrape with realistic market-rate pricing (£/person)
_CITY_PRICING = {
    "London":     {"Hotel": 135.0, "Catering": 30.0, "Conference": 55.0},
    "Edinburgh":  {"Hotel": 85.0,  "Catering": 22.0, "Conference": 40.0},
    "Manchester": {"Hotel": 75.0,  "Catering": 18.0, "Conference": 35.0},
    "Birmingham": {"Hotel": 70.0,  "Catering": 16.0, "Conference": 32.0},
    "Bristol":    {"Hotel": 80.0,  "Catering": 20.0, "Conference": 38.0},
    "Leeds":      {"Hotel": 65.0,  "Catering": 15.0, "Conference": 30.0},
    "Glasgow":    {"Hotel": 72.0,  "Catering": 17.0, "Conference": 33.0},
}

# Standard catering packages added to VendorPrice for each city
_CATERING_PACKAGES = [
    ("Working Lunch (pp)",            "Buffet",      12.0),
    ("3-Course Dinner (pp)",          "Dinner",      35.0),
    ("Morning Tea & Coffee (pp)",     "Beverages",    5.0),
    ("Full Day Delegate Package (pp)","Conference",  45.0),
    ("Drinks Reception (pp)",         "Reception",   20.0),
    ("Canapes x10 (pp)",              "Reception",   18.0),
    ("BBQ Buffet (pp)",               "Buffet",      22.0),
    ("Dietary Special (pp)",          "Specialist",  28.0),
]


# ── Overpass scraping ──────────────────────────────────────────────────────────

def _run_overpass(query: str) -> list:
    try:
        resp = requests.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=45,
            headers={"User-Agent": "EventManagerApp/1.0 (corporate-event-planner)"},
        )
        resp.raise_for_status()
        return resp.json().get("elements", [])
    except Exception as exc:
        logger.warning("Overpass request failed: %s", exc)
        return []


def _fetch_hotels(city: str) -> list[dict]:
    query = f"""
[out:json][timeout:30];
area["name"="{city}"]["admin_level"~"6|8"]->.a;
(
  node[tourism~"hotel|guest_house"](area.a);
  way[tourism~"hotel|guest_house"](area.a);
);
out center 30;
"""
    elements = _run_overpass(query)
    pricing = _CITY_PRICING.get(city, {"Hotel": 80.0})
    results = []
    seen = set()
    for el in elements:
        name = el.get("tags", {}).get("name") or el.get("tags", {}).get("brand")
        if not name or len(name) < 3 or name in seen:
            continue
        seen.add(name)
        stars = el.get("tags", {}).get("stars", "")
        desc = f"{stars}-star hotel in {city}" if stars else f"Hotel in {city}"
        results.append({
            "vendor_name": name[:150],
            "vendor_type": "Hotel",
            "city": city,
            "price_per_person": pricing["Hotel"],
            "currency": "GBP",
            "description": desc,
        })
    logger.info("Hotels scraped for %s: %d records", city, len(results))
    return results


def _fetch_caterers(city: str) -> list[dict]:
    query = f"""
[out:json][timeout:30];
area["name"="{city}"]["admin_level"~"6|8"]->.a;
(
  node[amenity="restaurant"][name](area.a);
  node[amenity="catering"][name](area.a);
);
out 25;
"""
    elements = _run_overpass(query)
    pricing = _CITY_PRICING.get(city, {"Catering": 18.0})
    results = []
    seen = set()
    for el in elements:
        name = el.get("tags", {}).get("name")
        if not name or len(name) < 3 or name in seen:
            continue
        seen.add(name)
        cuisine = el.get("tags", {}).get("cuisine", "")
        desc = f"{cuisine.title()} catering in {city}" if cuisine else f"Catering service in {city}"
        results.append({
            "vendor_name": name[:150],
            "vendor_type": "Catering",
            "city": city,
            "price_per_person": pricing["Catering"],
            "currency": "GBP",
            "description": desc[:300],
        })
    logger.info("Caterers scraped for %s: %d records", city, len(results))
    return results


# ── Price catalog ──────────────────────────────────────────────────────────────

def _build_price_catalog() -> list[dict]:
    """Generate catering package price records for every city."""
    catalog = []
    base_city = "Manchester"
    base_pricing = _CITY_PRICING[base_city]["Catering"]

    for city, tiers in _CITY_PRICING.items():
        multiplier = tiers["Catering"] / base_pricing
        for product, category, base_price in _CATERING_PACKAGES:
            catalog.append({
                "vendor_name": f"{city} Catering Services",
                "product_name": product,
                "price": round(base_price * multiplier, 2),
                "currency": "GBP",
                "category": category,
                "vendor_type": "Catering",
                "source_url": _OVERPASS_URL,
            })
    return catalog


# ── Database upserts ───────────────────────────────────────────────────────────

def _upsert_vendor(db, data: dict) -> bool:
    """Insert or update a Vendor row. Returns True if new."""
    from app.models.vendor import Vendor
    existing = (
        db.query(Vendor)
        .filter(Vendor.vendor_name == data["vendor_name"], Vendor.city == data["city"])
        .first()
    )
    if existing:
        existing.price_per_person = data["price_per_person"]
        existing.description = data.get("description", existing.description)
        existing.is_active = True
        return False
    db.add(Vendor(**data))
    return True


def _upsert_price(db, data: dict) -> bool:
    """Insert or update a VendorPrice row. Returns True if new."""
    from app.models.vendor import VendorPrice
    existing = (
        db.query(VendorPrice)
        .filter(
            VendorPrice.vendor_name == data["vendor_name"],
            VendorPrice.product_name == data["product_name"],
        )
        .first()
    )
    if existing:
        existing.price = data["price"]
        existing.crawled_at = datetime.now(timezone.utc)
        return False
    db.add(VendorPrice(**data, crawled_at=datetime.now(timezone.utc)))
    return True


# ── Main entry point ───────────────────────────────────────────────────────────

def run_crawl() -> dict:
    """
    Scrape hotels and catering vendors for all configured UK cities,
    then upsert results into Vendor and VendorPrice tables.
    Called by the weekly scheduler and the /vendors/crawl endpoint.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    vendors_new = vendors_updated = prices_new = prices_updated = 0

    try:
        for city in _CITY_PRICING:
            # Hotels
            for record in _fetch_hotels(city):
                if _upsert_vendor(db, record):
                    vendors_new += 1
                else:
                    vendors_updated += 1
            time.sleep(2)  # respect Overpass rate limit between cities

            # Caterers
            for record in _fetch_caterers(city):
                if _upsert_vendor(db, record):
                    vendors_new += 1
                else:
                    vendors_updated += 1
            time.sleep(2)

        # Catering price catalog (no HTTP calls, purely computed)
        for record in _build_price_catalog():
            if _upsert_price(db, record):
                prices_new += 1
            else:
                prices_updated += 1

        db.commit()
        summary = {
            "status": "ok",
            "vendors_new": vendors_new,
            "vendors_updated": vendors_updated,
            "prices_new": prices_new,
            "prices_updated": prices_updated,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Vendor crawl complete: %s", summary)
        return summary

    except Exception as exc:
        db.rollback()
        logger.error("Vendor crawl failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()
