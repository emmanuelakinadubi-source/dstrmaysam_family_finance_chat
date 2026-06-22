"""Agent 4 – Recommendation Agent.

Generates user-friendly VenueCard objects and an AI-powered summary.
Uses a single batched LLM call to produce recommendation reasons for all
top venues, avoiding N+1 LLM round-trips.
"""
import json
import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.core.config import settings
from app.schemas.event import EventRequirements, RecommendationSummary, VenueCard
from app.tools.summary import generate_summary

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an Event Planning AI Assistant.

Given event requirements and a list of venues, return recommendation reasons as JSON.
Use ONLY the venue information provided. Do not invent details.
Each reason should be 2-3 sentences citing specific venue attributes."""


def generate_recommendations(
    requirements: EventRequirements,
    ranked_venues: List[Dict[str, Any]],
) -> Tuple[List[VenueCard], RecommendationSummary]:
    top_venues = ranked_venues[:10]
    reasons = _batch_reasons(requirements, top_venues)

    venue_cards: List[VenueCard] = []
    for i, venue_data in enumerate(top_venues):
        meta = venue_data.get("metadata", {})

        min_price = _to_float(meta.get("min_price"))
        max_price = _to_float(meta.get("max_price"))
        if requirements.max_budget > 0:
            compat = "Within budget" if min_price <= requirements.max_budget else "Exceeds budget"
        else:
            compat = f"£{min_price:,.0f} – £{max_price:,.0f}"

        image_raw = meta.get("images", "")
        image_url = image_raw.split(",")[0].strip() if image_raw else ""

        venue_cards.append(
            VenueCard(
                venue_id=meta.get("venue_id", ""),
                venue_name=meta.get("venue_name", "Unknown"),
                venue_image=image_url,
                city=meta.get("city", ""),
                capacity=f"Up to {meta.get('capacity', '0')} guests",
                budget_compatibility=compat,
                venue_description=venue_data.get("text", "")[:350],
                venue_features=[],
                match_score=round(venue_data.get("match_score", 0.0), 1),
                recommendation_reason=reasons[i] if i < len(reasons) else _fallback_reason(meta),
            )
        )

    summary = generate_summary(requirements, ranked_venues)
    return venue_cards, summary


def _batch_reasons(
    requirements: EventRequirements,
    venues: List[Dict[str, Any]],
) -> List[str]:
    if not venues:
        return []

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
        f"Event: {requirements.attendees} guests in {requirements.city or 'any city'}, "
        f"budget £{requirements.min_budget:,.0f}–£{requirements.max_budget:,.0f}\n\n"
        + "\n\n".join(venue_lines)
        + '\n\nReturn JSON: {"reasons": ["reason1", "reason2", ...]}'
    )

    try:
        messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = _get_llm().invoke(messages)
        raw = re.search(r"\{.*\}", response.content, re.DOTALL)
        if raw:
            data = json.loads(raw.group(0))
            reasons = data.get("reasons", [])
            # Pad with fallbacks for venues beyond top-5
            for i in range(len(reasons), len(venues)):
                reasons.append(_fallback_reason(venues[i].get("metadata", {})))
            return reasons
    except Exception as exc:
        logger.error("Batch reason generation failed: %s", exc)

    return [_fallback_reason(v.get("metadata", {})) for v in venues]


def _fallback_reason(meta: Dict) -> str:
    return (
        f"This venue in {meta.get('city', 'the requested city')} "
        f"has a capacity of {meta.get('capacity', '0')} guests "
        f"and is within the selected price range."
    )


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.5,
    )
