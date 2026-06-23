import os
import requests
from typing import Optional, List, Any

BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/api/v1")


def _get(path: str, params: dict = None) -> Any:
    r = requests.get(f"{BASE_URL}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def _post(path: str, payload: dict) -> Any:
    r = requests.post(f"{BASE_URL}{path}", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Health ─────────────────────────────────────────────────────────────────────

def get_health() -> dict:
    return _get("/health")


# ── Events ─────────────────────────────────────────────────────────────────────

def list_events(skip: int = 0, limit: int = 50) -> List[dict]:
    return _get("/events/", {"skip": skip, "limit": limit})


def get_event(event_id: str) -> dict:
    return _get(f"/events/{event_id}")


def get_event_recommendations(event_id: str) -> dict:
    return _get(f"/events/{event_id}/recommendations")


def get_dashboard_stats() -> dict:
    try:
        stats = _get("/events/dashboard/stats")
        try:
            vendors = list_vendors()
            stats["total_vendors"] = len(vendors)
        except Exception:
            stats["total_vendors"] = 0
        return stats
    except Exception:
        return {"total_events": 0, "total_budget": 0.0, "total_vendors": 0, "recent_events": []}


# ── Company Events & Budgets ───────────────────────────────────────────────────

def create_event(
    event_name: str,
    event_date: str,
    attendee_count: int,
    budget: float,
    venue: str = None,
    hotel: str = None,
    food_requirements: str = None,
    welfare_budget: float = None,
    location: str = None,
    special_requirements: str = None,
) -> dict:
    return _post("/company/events", {
        "event_name": event_name,
        "event_date": event_date,
        "attendee_count": attendee_count,
        "budget": budget,
        "venue": venue,
        "hotel": hotel,
        "food_requirements": food_requirements,
        "welfare_budget": welfare_budget,
        "location": location,
        "special_requirements": special_requirements,
    })


def create_company_budget(
    title: str,
    total_budget: float,
    department: str = None,
    period_start: str = None,
    period_end: str = None,
) -> dict:
    return _post("/company/budgets", {
        "title": title,
        "total_budget": total_budget,
        "department": department,
        "period_start": period_start,
        "period_end": period_end,
    })


def list_company_budgets() -> List[dict]:
    return _get("/company/budgets")


# ── Vendors ────────────────────────────────────────────────────────────────────

def list_vendors(city: str = None, vendor_type: str = None) -> List[dict]:
    params = {}
    if city:
        params["city"] = city
    if vendor_type:
        params["vendor_type"] = vendor_type
    return _get("/vendors/list", params)


def match_vendors(budget: float, attendees: int, vendor_type: str) -> List[dict]:
    return _post("/vendors/match", {
        "budget": budget,
        "attendees": attendees,
        "vendor_type": vendor_type,
    })


def get_vendor_ai_recommendation(
    city: str,
    attendee_count: int,
    budget: float,
    number_of_days: int = 1,
    food_required: bool = True,
    hosting_required: bool = True,
) -> dict:
    return _post("/vendor-ai/recommend", {
        "city": city,
        "attendee_count": attendee_count,
        "budget": budget,
        "number_of_days": number_of_days,
        "food_required": food_required,
        "hosting_required": hosting_required,
    })


def list_vendor_prices(vendor_type: str = None, category: str = None) -> List[dict]:
    params = {}
    if vendor_type:
        params["vendor_type"] = vendor_type
    if category:
        params["category"] = category
    return _get("/vendors/prices", params)


def compare_vendors(vendor_names: List[str], category: str = None) -> List[dict]:
    params = {"vendors": ",".join(vendor_names)}
    if category:
        params["category"] = category
    return _get("/vendors/compare", params)


def trigger_vendor_crawl() -> dict:
    return _post("/vendors/crawl", {})


def get_crawl_schedule() -> dict:
    return _get("/vendors/crawl/schedule")


# ── Reports & Analytics ────────────────────────────────────────────────────────

def get_family_summary(year: int) -> dict:
    return _get("/reports/family/summary", {"year": year})


def get_vendor_analysis(category: str = None) -> List[dict]:
    params = {}
    if category:
        params["category"] = category
    return _get("/reports/vendors/analysis", params)


def get_family_trends() -> List[dict]:
    return _get("/analytics/family/trends")


def get_category_breakdown(year: int) -> List[dict]:
    return _get("/analytics/family/category-breakdown", {"year": year})


def get_vendor_price_trends(vendor_type: str = "grocery") -> List[dict]:
    return _get("/analytics/vendors/price-trends", {"vendor_type": vendor_type})
