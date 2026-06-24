"""
Data cleaning and guardrail pipeline for scraped vendor data.

Guardrails (applied in order):
  1. Location guardrail — STRICT. Only vendors confirmed inside the event radius pass.
     Web-scraped vendors with no geocoded location are matched by postcode area prefix.
     Vendors with NO postcode AND no distance are dropped (too risky to include).
  2. Delivery extension — vendors beyond radius are kept ONLY if they explicitly offer
     delivery AND are within 3x the search radius (capped at 100 km).
  3. Budget filter — drop vendors whose estimated cost exceeds per-head budget.
  4. Food-category filter — keep vendors with matching OR unknown dietary tags.
  5. Name normalisation + deduplication.

Key principle: it is better to show fewer, correct-location results and prompt the
user to widen radius or explore nearby towns than to flood them with results from
Manchester or London when the event is in Chelmsford.
"""
from __future__ import annotations

import re
import unicodedata
import logging
from typing import List, Optional

from app.modules.vendors.smart_scraper import EventScraperConfig, ScrapedVendor

logger = logging.getLogger(__name__)

_CATERING_BUDGET_RATIO = 0.30
_HOTEL_BUDGET_RATIO    = 0.25

# Maximum distance for delivery vendors (radius * this multiplier, max 100 km)
_DELIVERY_RADIUS_MULTIPLIER = 3.0


# ── Postcode area helpers ─────────────────────────────────────────────────────

def _postcode_outward(postcode: str) -> str:
    """
    Extract the outward code from a UK postcode.
    'CM1 6GQ' → 'CM1',  'M4 3AH' → 'M4',  'SW1A 1AA' → 'SW1A'
    """
    clean = postcode.replace(" ", "").upper()
    # Inward code is always exactly 3 chars; outward is the rest
    if len(clean) > 3:
        return clean[:-3]
    return clean


def _postcode_area(postcode: str) -> str:
    """
    Extract just the letter-prefix area from a UK postcode.
    'CM1 6GQ' → 'CM',  'M4 3AH' → 'M',  'SW1A 1AA' → 'SW'
    """
    outward = _postcode_outward(postcode)
    return re.match(r"^[A-Z]+", outward).group() if outward else ""


def _location_matches_event(vendor: ScrapedVendor, config: EventScraperConfig) -> tuple[bool, str]:
    """
    Return (passes_guardrail, reason_string).

    Decision tree:
      1. Geocoded distance available (from postcode OR address geocoding):
         a. Within radius → pass
         b. Beyond radius, delivery-capable, within 3x radius → pass (delivery)
         c. Beyond radius and no delivery → FAIL
      2. No geocoded distance (location lookup failed entirely):
         a. Vendor postcode outward matches event → pass (same district)
         b. Vendor postcode area matches event area → pass (same postal area)
         c. Vendor has a non-matching postcode → FAIL (different city)
         d. Vendor has address but geocoding failed → try city/town name matching
         e. No postcode and no address → FAIL (completely unverifiable)
    """
    event_outward   = _postcode_outward(config.postcode)
    event_area      = _postcode_area(config.postcode)
    max_delivery_km = min(config.radius_km * _DELIVERY_RADIUS_MULTIPLIER, 100.0)

    # ── Path 1: distance is known (via postcode OR Nominatim address geocode) ─
    if vendor.distance_km > 0:
        if vendor.distance_km <= config.radius_km:
            return True, "within_radius"
        if vendor.delivery_available and vendor.distance_km <= max_delivery_km:
            return True, f"delivery_{vendor.distance_km:.1f}km"
        return False, f"out_of_area_{vendor.distance_km:.1f}km"

    # ── Path 2: distance unknown — try postcode area matching ────────────────
    if vendor.postcode:
        vendor_outward = _postcode_outward(vendor.postcode)
        vendor_area    = _postcode_area(vendor.postcode)
        if vendor_outward == event_outward:
            return True, "same_district"
        if vendor_area == event_area:
            return True, "same_postcode_area"
        return False, f"wrong_postcode_area_{vendor_area}_vs_{event_area}"

    # ── Path 3: no postcode — try city/town name from address ────────────────
    if vendor.address:
        # Check if the event city or postcode area towns appear in the address
        addr_lower = vendor.address.lower()
        city_lower = (config.city or "").lower()

        # Match against event city
        if city_lower and city_lower in addr_lower:
            return True, "address_city_match"

        # Match against known towns in the same postcode area (e.g. CM = Chelmsford/Braintree/etc.)
        # Simple heuristic: if the address mentions the county, accept it tentatively
        # (will still be verified by name dedup and user review)
        county_hints = {
            "CM": ["essex", "chelmsford", "braintree", "witham", "colchester", "harlow"],
            "CO": ["essex", "colchester"],
            "SS": ["essex", "southend"],
            "IG": ["essex", "ilford"],
            "EN": ["hertfordshire", "enfield"],
            "AL": ["hertfordshire", "st albans"],
            "SG": ["hertfordshire"],
            "CB": ["cambridgeshire", "cambridge"],
            "IP": ["suffolk", "ipswich"],
            "NR": ["norfolk", "norwich"],
        }
        area_towns = county_hints.get(event_area, [])
        if any(town in addr_lower for town in area_towns):
            return True, "address_county_match"

        return False, "address_does_not_match_area"

    # ── Path 4: no postcode, no address — completely unverifiable ────────────
    return False, "no_location_info"


# ── Budget guardrail ──────────────────────────────────────────────────────────

def _within_budget(vendor: ScrapedVendor, config: EventScraperConfig) -> bool:
    if vendor.price_per_head is None:
        return True   # unknown price → include (don't discard unknowns)
    attendees = max(config.attendees, 1)
    if vendor.vendor_type == "catering":
        budget = config.catering_budget or (config.total_budget * _CATERING_BUDGET_RATIO)
    else:
        budget = config.hotel_budget or (config.total_budget * _HOTEL_BUDGET_RATIO)
    per_head = budget / attendees if attendees else 0
    return vendor.price_per_head <= per_head


# ── Dietary guardrail ─────────────────────────────────────────────────────────

def _matches_food_categories(vendor: ScrapedVendor, required: List[str]) -> bool:
    """
    Only drop a vendor if it has EXPLICIT specializations AND none match.
    Vendors with no dietary tags pass through (most restaurants have no OSM diet info).
    """
    if not required or vendor.vendor_type == "hotel":
        return True
    if not vendor.specializations:
        return True   # unknown ≠ incompatible
    vendor_specs = {s.lower() for s in vendor.specializations}
    return bool(vendor_specs.intersection(r.lower() for r in required))


# ── Price estimation ──────────────────────────────────────────────────────────

_CITY_PRICE_ESTIMATES = {
    "london":        {"catering": 25.0, "hotel": 135.0},
    "manchester":    {"catering": 12.0, "hotel": 75.0},
    "birmingham":    {"catering": 10.0, "hotel": 70.0},
    "edinburgh":     {"catering": 15.0, "hotel": 85.0},
    "bristol":       {"catering": 12.0, "hotel": 80.0},
    "leeds":         {"catering": 10.0, "hotel": 65.0},
    "glasgow":       {"catering": 11.0, "hotel": 72.0},
    "sheffield":     {"catering":  9.0, "hotel": 60.0},
    "liverpool":     {"catering": 10.0, "hotel": 65.0},
    "chelmsford":    {"catering": 11.0, "hotel": 68.0},
    "colchester":    {"catering": 10.0, "hotel": 62.0},
    "southend":      {"catering": 10.0, "hotel": 60.0},
    "cambridge":     {"catering": 14.0, "hotel": 80.0},
    "ipswich":       {"catering": 10.0, "hotel": 60.0},
    "norwich":       {"catering": 10.0, "hotel": 62.0},
}
_DEFAULT_PRICE = {"catering": 12.0, "hotel": 80.0}


def _cuisine_price_override(vendor: ScrapedVendor) -> Optional[float]:
    """Fast food chains are cheap — use known per-head estimates."""
    text = ((vendor.cuisine or "") + " " + (vendor.name or "")).lower()
    for kw in ["mcdonald", "kfc", "subway", "domino", "pizza hut", "greggs",
                "pret", "leon", "five guys", "burger king", "nando", "fast food"]:
        if kw in text:
            return 8.0
    return None


def _estimate_price(vendor: ScrapedVendor, city: str) -> Optional[float]:
    estimates = _CITY_PRICE_ESTIMATES.get(city.lower(), _DEFAULT_PRICE)
    return estimates.get(vendor.vendor_type)


# ── Name normalisation ────────────────────────────────────────────────────────

def _normalise_name(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w\s\-&'()]", "", name)
    return re.sub(r"\s+", " ", name).strip().title()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    raw_vendors: List[ScrapedVendor],
    config: EventScraperConfig,
) -> List[ScrapedVendor]:
    """
    Apply all guardrail steps. Returns location-verified, deduplicated, sorted list.
    """
    logger.info("Pipeline start: %d raw vendors for postcode %s", len(raw_vendors), config.postcode)

    cleaned: List[ScrapedVendor] = []
    seen_slugs: set[str] = set()
    dropped_location = 0

    for v in raw_vendors:
        # 1 ── STRICT location guardrail
        passes, reason = _location_matches_event(v, config)
        if not passes:
            logger.debug("Location guardrail DROPPED %s | postcode=%s | reason=%s",
                         v.name, v.postcode, reason)
            dropped_location += 1
            continue

        # 2 ── Name normalisation
        v.name = _normalise_name(v.name)
        if not v.name:
            continue

        # 3 ── Deduplication
        slug = _slug(v.name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # 4 ── Price estimation
        if v.price_per_head is None:
            chain_override = _cuisine_price_override(v)
            v.price_per_head = chain_override if chain_override else _estimate_price(v, config.city)

        # 5 ── Budget guardrail
        if not _within_budget(v, config):
            logger.debug("Budget guardrail dropped: %s (£%.0f/head)", v.name, v.price_per_head or 0)
            continue

        # 6 ── Food category guardrail
        if not _matches_food_categories(v, config.food_categories):
            logger.debug("Diet guardrail dropped: %s", v.name)
            continue

        cleaned.append(v)

    logger.info(
        "Pipeline complete: %d passed | %d dropped by location guardrail | %d raw total",
        len(cleaned), dropped_location, len(raw_vendors),
    )

    # Sort: in-radius by distance first, delivery vendors after
    cleaned.sort(key=lambda v: (
        "delivery" in (v.source or ""),
        v.distance_km if v.distance_km > 0 else 999,
    ))
    return cleaned
