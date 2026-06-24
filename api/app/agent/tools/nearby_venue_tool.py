import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.agent.tools.recommendation_tool import _batch_reasons, _build_venue_card, _fallback_reason
from app.schemas.event import EventRequirements
from app.tools.ranking import rank_venues
from app.tools.retrieval import retrieve_venues

logger = logging.getLogger(__name__)


class NearbyVenueInput(BaseModel):
    city: str = Field(default="", description="Preferred city (will broaden to nationwide if no matches)")
    attendees: int = Field(default=0, description="Number of guests (relaxed to 80% capacity match)")
    target_budget: float = Field(default=0.0, description="Target budget in GBP (relaxed to 150% tolerance)")
    additional_requirements: str = Field(
        default="",
        description="Comma-separated requirements. Partial matching applied.",
    )


def _find_nearby_fn(
    city: str = "",
    attendees: int = 0,
    target_budget: float = 0.0,
    additional_requirements: str = "",
) -> str:
    """
    Fallback venue search with relaxed budget/capacity constraints.

    IMPORTANT: city constraint is NEVER dropped.  We do not suggest venues in
    Manchester or London for a Chelmsford event.  If no venues are found for the
    requested city in the indexed database, we return 0 and tell the user to use
    the live web-scraper tab to discover real local hotels and venues.
    """
    reqs = EventRequirements(
        city=city,
        attendees=int(attendees * 0.8) if attendees > 0 else 0,
        min_budget=0,
        max_budget=target_budget * 1.5 if target_budget > 0 else 0,
        additional_requirements=[r.strip() for r in additional_requirements.split(",") if r.strip()],
    )

    query_parts = ["event venue conference"]
    if city:
        query_parts.append(city)
    if attendees > 0:
        query_parts.append(f"{attendees} guests")
    if additional_requirements:
        query_parts.append(additional_requirements)
    query = " ".join(query_parts)

    # Always keep the city filter — never broaden to nationwide
    chunks = retrieve_venues(query=query, city=city.strip() if city else None, top_k=20)
    ranked = rank_venues(chunks, reqs, relaxed=True)
    reasons = _batch_reasons(reqs, ranked[:5])

    venues = []
    for i, v in enumerate(ranked[:5]):
        meta = v.get("metadata", {})
        reason = (reasons[i] if i < len(reasons) else _fallback_reason(meta))
        venues.append(_build_venue_card(v, meta, reqs, reason, is_fallback=True))

    if not venues:
        # Honest empty result — guide the user to the live scraper
        empty_summary = {
            "total_venues": 0,
            "best_venue": "None found in indexed database",
            "budget_analysis": "No pre-indexed venues found for this city",
            "capacity_analysis": "Use the live web scraper to find real local venues",
            "key_recommendations": [
                f"No venues for '{city}' are currently in the indexed database.",
                "Use the 'Find Local Caterers & Hotels' section and click "
                "'Search Web + Map for Nearby Vendors' to discover real local venues and hotels.",
                "The web scraper searches DuckDuckGo + OpenStreetMap in real time "
                "and indexes the results for your event.",
            ],
        }
        return json.dumps({"venues": [], "summary": empty_summary, "is_fallback": True})

    alt_notes = [
        f"These venues in or near {city} have relaxed budget/capacity matching applied.",
    ]
    if target_budget > 0:
        alt_notes.append(f"Budget tolerance extended to £{target_budget * 1.5:,.0f} (150%)")
    if attendees > 0:
        alt_notes.append(f"Venues with at least 80% of {attendees}-guest capacity included")

    best = venues[0]["venue_name"]
    summary = {
        "total_venues": len(venues),
        "best_venue": best,
        "budget_analysis": (
            f"Alternatives within £{target_budget * 1.5:,.0f} (150% of target)"
            if target_budget > 0 else "No budget constraints applied"
        ),
        "capacity_analysis": (
            f"Venues with 80%+ of required {attendees} capacity"
            if attendees > 0 else "No capacity constraints applied"
        ),
        "key_recommendations": alt_notes,
    }

    return json.dumps({"venues": venues, "summary": summary, "is_fallback": True})


find_nearby_venues = StructuredTool.from_function(
    func=_find_nearby_fn,
    name="find_nearby_venues",
    description=(
        "Find alternative venues when exact requirements cannot be met. "
        "Automatically relaxes: budget tolerance to 150%, capacity to 80%, and broadens location if needed. "
        "Priority order: (1) budget match, (2) capacity match, (3) location, (4) features. "
        "ALWAYS call this when recommend_venues returns 0 results or all scores < 40. "
        "Never return empty results to the user — always use this as a fallback."
    ),
    args_schema=NearbyVenueInput,
)
