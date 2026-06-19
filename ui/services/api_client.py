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


def _post_file(path: str, file_obj) -> Any:
    files = {"file": (file_obj.name, file_obj.getvalue(), file_obj.type)}
    r = requests.post(f"{BASE_URL}{path}", files=files, timeout=60)
    r.raise_for_status()
    return r.json()


# ── Health ─────────────────────────────────────────────────────────────────────

def get_health() -> dict:
    return _get("/health")


# ── Events ─────────────────────────────────────────────────────────────────────

def upload_event_plan(file_obj) -> dict:
    """Upload a document file and run the AI extraction pipeline."""
    return _post_file("/events/upload", file_obj)


def list_events(skip: int = 0, limit: int = 50) -> List[dict]:
    return _get("/events/", {"skip": skip, "limit": limit})


def get_event(event_id: str) -> dict:
    return _get(f"/events/{event_id}")


def get_event_recommendations(event_id: str) -> dict:
    return _get(f"/events/{event_id}/recommendations")


def get_dashboard_stats() -> dict:
    try:
        stats = _get("/events/dashboard/stats")
        # Add vendor count
        try:
            vendors = list_vendors()
            stats["total_vendors"] = len(vendors)
        except Exception:
            stats["total_vendors"] = 0
        return stats
    except Exception:
        return {"total_events": 0, "total_budget": 0.0, "total_vendors": 0, "recent_events": []}


# ── Vendors ────────────────────────────────────────────────────────────────────

def list_vendors(city: str = None, vendor_type: str = None) -> List[dict]:
    params = {}
    if city:
        params["city"] = city
    if vendor_type:
        params["vendor_type"] = vendor_type
    return _get("/vendors/list", params)


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


# ── Event Chat (RAG Agent) ─────────────────────────────────────────────────────

def event_chat(question: str, event_id: str = None, evaluate: bool = False) -> dict:
    return _post("/event-chat/", {
        "question": question,
        "event_id": event_id,
        "evaluate": evaluate,
    })


# ── General Chat (session-based) ───────────────────────────────────────────────

def send_chat_message(message: str, module: str = "company", session_id: str = None) -> dict:
    payload = {"message": message, "module": module}
    if session_id:
        payload["session_id"] = session_id
    return _post("/chat/", payload)


def list_chat_sessions() -> List[dict]:
    return _get("/chat/sessions")


# ── Family Finance (Phase 2) ───────────────────────────────────────────────────

def calculate_allocation(husband_income: float, wife_income: float, month: str, year: int) -> dict:
    return _post("/family/calculate", {
        "husband_income": husband_income, "wife_income": wife_income,
        "month": month, "year": year,
    })


def create_budget(month: str, year: int, husband_income: float, wife_income: float,
                  expenses: List[dict] = None, notes: str = None) -> dict:
    return _post("/family/budgets", {
        "month": month, "year": year,
        "husband_income": husband_income, "wife_income": wife_income,
        "expenses": expenses or [], "notes": notes,
    })


def list_budgets() -> List[dict]:
    return _get("/family/budgets")


def get_budget(budget_id: str) -> dict:
    return _get(f"/family/budgets/{budget_id}")


def add_expense(budget_id: str, category: str, amount: float,
                description: str = None, vendor: str = None) -> dict:
    return _post(f"/family/budgets/{budget_id}/expenses", {
        "category": category, "amount": amount,
        "description": description, "vendor": vendor,
    })


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
