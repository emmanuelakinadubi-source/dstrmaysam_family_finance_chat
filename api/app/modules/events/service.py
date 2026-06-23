"""Vendor recommendation service for event plans."""
import logging

logger = logging.getLogger(__name__)


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
