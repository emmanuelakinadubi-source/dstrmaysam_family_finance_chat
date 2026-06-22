import json
import logging
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.event import EventRequirements
from app.tools.ranking import rank_venues
from app.tools.retrieval import retrieve_venues

logger = logging.getLogger(__name__)

_REASON_SYSTEM_PROMPT = """You are an Event Planning AI Assistant.
Given event requirements and a list of venues, return recommendation reasons as JSON.
Use ONLY the venue information provided. Do not invent details.
Each reason must be 2-3 sentences citing specific venue attributes."""


class RecommendVenuesInput(BaseModel):
    city: str = Field(default="", description="City or location for the event")
    attendees: int = Field(default=0, description="Number of expected guests")
    min_budget: float = Field(default=0.0, description="Minimum budget in GBP (0 if not specified)")
    max_budget: float = Field(default=0.0, description="Maximum budget in GBP (0 if not specified)")
    event_date: str = Field(default="", description="Event date in YYYY-MM-DD format")
    additional_requirements: str = Field(
        default="",
        description="Comma-separated special requirements e.g. 'AV equipment, parking, catering'",
    )


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_bool(metadata: Dict, key: str):
    v = metadata.get(key)
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "yes", "1")


def _build_venue_card(v: Dict, meta: Dict, reqs: EventRequirements, reason: str, is_fallback: bool = False) -> Dict:
    min_price = _to_float(meta.get("min_price"))
    max_price = _to_float(meta.get("max_price"))
    if reqs.max_budget > 0:
        compat = "Within budget" if min_price <= reqs.max_budget else "Exceeds budget"
    else:
        compat = f"£{min_price:,.0f} – £{max_price:,.0f}"

    image_raw = meta.get("images", "")
    image_url = image_raw.split(",")[0].strip() if image_raw else ""

    features_raw = meta.get("features", "")
    features = [f.strip() for f in features_raw.split(",") if f.strip()][:5]

    event_types_raw = meta.get("event_types", "")
    event_types = [t.strip() for t in event_types_raw.split(",") if t.strip()][:5]

    return {
        "venue_id": meta.get("venue_id", ""),
        "venue_name": meta.get("venue_name", "Unknown"),
        "venue_image": image_url,
        "city": meta.get("city", ""),
        "postcode": meta.get("postcode", ""),
        "capacity": f"Up to {meta.get('capacity', '0')} guests",
        "budget_compatibility": compat,
        "venue_description": v.get("text", "")[:350],
        "venue_features": features,
        "event_types": event_types,
        "venue_url": meta.get("venue_url", ""),
        "match_score": round(v.get("match_score", 0.0), 1),
        "score_breakdown": v.get("score_breakdown", {}),
        "recommendation_reason": reason,
        "is_fallback": is_fallback,
        "parking": _parse_bool(meta, "parking"),
        "wifi": _parse_bool(meta, "wifi"),
        "av_equipment": _parse_bool(meta, "av_equipment"),
        "hybrid_events": _parse_bool(meta, "hybrid_events"),
        "live_streaming": _parse_bool(meta, "live_streaming"),
        "catering": _parse_bool(meta, "catering"),
        "alcohol_license": _parse_bool(meta, "alcohol_license"),
        "accommodation": _parse_bool(meta, "accommodation"),
        "outdoor_space": _parse_bool(meta, "outdoor_space"),
        "wheelchair_access": _parse_bool(meta, "wheelchair_access"),
        "nearest_train": meta.get("nearest_train", ""),
        "nearest_underground": meta.get("nearest_underground", ""),
        "nearest_parking": meta.get("nearest_parking", ""),
        "response_rate": meta.get("response_rate", ""),
        "response_time": meta.get("response_time", ""),
        "sustainability": meta.get("sustainability", ""),
    }


def _batch_reasons(reqs: EventRequirements, venues: List[Dict]) -> List[str]:
    if not venues:
        return []
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.4,
    )
    venue_lines = []
    for i, v in enumerate(venues[:5], 1):
        meta = v.get("metadata", {})
        venue_lines.append(
            f"Venue {i}: {meta.get('venue_name', 'Unknown')}\n"
            f"City: {meta.get('city', '')}, Capacity: {meta.get('capacity', '0')}, "
            f"Price: £{_to_float(meta.get('min_price')):,.0f}–£{_to_float(meta.get('max_price')):,.0f}\n"
            f"Details: {v.get('text', '')[:300]}"
        )
    prompt = (
        f"Event: {reqs.attendees} guests in {reqs.city or 'any city'}, "
        f"budget £{reqs.min_budget:,.0f}–£{reqs.max_budget:,.0f}\n"
        f"Requirements: {', '.join(reqs.additional_requirements)}\n\n"
        + "\n\n".join(venue_lines)
        + '\n\nReturn JSON: {"reasons": ["reason1", "reason2", ...]}'
    )
    try:
        response = llm.invoke([SystemMessage(content=_REASON_SYSTEM_PROMPT), HumanMessage(content=prompt)])
        match = re.search(r"\{.*\}", response.content, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            reasons = data.get("reasons", [])
            for i in range(len(reasons), len(venues)):
                reasons.append(_fallback_reason(venues[i].get("metadata", {})))
            return reasons
    except Exception as exc:
        logger.error("Batch reason generation failed: %s", exc)
    return [_fallback_reason(v.get("metadata", {})) for v in venues]


def _fallback_reason(meta: Dict) -> str:
    return (
        f"This venue in {meta.get('city', 'the area')} accommodates "
        f"up to {meta.get('capacity', '0')} guests "
        f"and fits within your budget range."
    )


def _recommend_fn(
    city: str = "",
    attendees: int = 0,
    min_budget: float = 0.0,
    max_budget: float = 0.0,
    event_date: str = "",
    additional_requirements: str = "",
) -> str:
    reqs = EventRequirements(
        city=city,
        attendees=attendees,
        min_budget=min_budget,
        max_budget=max_budget,
        event_date=event_date,
        additional_requirements=[r.strip() for r in additional_requirements.split(",") if r.strip()],
    )

    query_parts = ["event venue"]
    if city:
        query_parts.append(city)
    if attendees > 0:
        query_parts.append(f"{attendees} guests")
    if max_budget > 0:
        query_parts.append(f"budget £{max_budget:,.0f}")
    if additional_requirements:
        query_parts.append(additional_requirements)
    query = " ".join(query_parts)

    chunks = retrieve_venues(query=query, city=city.strip() if city else None, top_k=15)
    ranked = rank_venues(chunks, reqs)
    reasons = _batch_reasons(reqs, ranked[:10])

    venues = []
    for i, v in enumerate(ranked[:10]):
        meta = v.get("metadata", {})
        reason = reasons[i] if i < len(reasons) else _fallback_reason(meta)
        venues.append(_build_venue_card(v, meta, reqs, reason, is_fallback=False))

    total = len(ranked)
    in_budget = sum(1 for v in venues if "Within" in v.get("budget_compatibility", ""))
    best = venues[0]["venue_name"] if venues else "No venues found"

    summary = {
        "total_venues": total,
        "best_venue": best,
        "budget_analysis": (
            f"{in_budget} of {len(venues)} venues within £{max_budget:,.0f} budget"
            if max_budget > 0 else "Budget not specified"
        ),
        "capacity_analysis": (
            f"{len(venues)} venues can accommodate {attendees}+ guests"
            if attendees > 0 else "Capacity not specified"
        ),
        "key_recommendations": [
            f"Best match: {best} ({venues[0]['match_score']}/100)" if venues else "No matches found",
            f"Average match score: {sum(v['match_score'] for v in venues) / len(venues):.1f}/100" if venues else "N/A",
        ],
    }

    return json.dumps({"venues": venues, "summary": summary, "is_fallback": False})


recommend_venues = StructuredTool.from_function(
    func=_recommend_fn,
    name="recommend_venues",
    description=(
        "Find, rank, and recommend venues that match the given event requirements. "
        "Uses 40/20/15/10/10/5 weighted scoring (capacity/budget/location/event_type/features/business). "
        "Returns JSON with ranked venues, match scores, score breakdowns, and a summary. "
        "Call this after extract_event_requirements. "
        "If it returns 0 venues or all scores are below 40, call find_nearby_venues as fallback."
    ),
    args_schema=RecommendVenuesInput,
)
