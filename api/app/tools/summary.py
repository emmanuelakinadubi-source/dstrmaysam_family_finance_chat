from typing import Any, Dict, List

from app.schemas.event import EventRequirements, RecommendationSummary


def _fits_budget(meta: Dict, req: EventRequirements) -> bool:
    try:
        min_price = float(meta.get("min_price") or 0)
        return req.max_budget <= 0 or min_price <= req.max_budget
    except (TypeError, ValueError):
        return True


def _fits_capacity(meta: Dict, req: EventRequirements) -> bool:
    try:
        cap = int(meta.get("capacity") or 0)
        return req.attendees <= 0 or cap <= 0 or cap >= req.attendees
    except (TypeError, ValueError):
        return True


def generate_summary(
    requirements: EventRequirements,
    ranked_venues: List[Dict[str, Any]],
) -> RecommendationSummary:
    if not ranked_venues:
        return RecommendationSummary(
            total_venues=0,
            best_venue="No venues found",
            budget_analysis="No venues matched your criteria",
            capacity_analysis="No capacity data available",
            key_recommendations=["Try broadening your search criteria or adjusting the budget range"],
        )

    top = ranked_venues[0]
    top_meta = top.get("metadata", {})
    top_name = top_meta.get("venue_name", "Unknown")

    budget_count = sum(1 for v in ranked_venues if _fits_budget(v.get("metadata", {}), requirements))
    cap_count = sum(1 for v in ranked_venues if _fits_capacity(v.get("metadata", {}), requirements))

    budget_text = (
        f"{budget_count} of {len(ranked_venues)} venues fit your budget"
        + (f" of £{requirements.min_budget:,.0f} – £{requirements.max_budget:,.0f}" if requirements.max_budget > 0 else "")
    )
    cap_text = (
        f"{cap_count} venues can accommodate {requirements.attendees} attendees"
        if requirements.attendees > 0
        else f"{cap_count} venues have confirmed capacity"
    )

    recs = [
        f"Top pick: {top_name} (score {top.get('match_score', 0):.1f}/100)",
    ]
    if len(ranked_venues) > 1:
        runner_up = ranked_venues[1].get("metadata", {}).get("venue_name", "N/A")
        recs.append(f"Runner-up: {runner_up}")
    if requirements.city:
        recs.append(f"Filtered for venues in {requirements.city}")

    return RecommendationSummary(
        total_venues=len(ranked_venues),
        best_venue=top_name,
        budget_analysis=budget_text,
        capacity_analysis=cap_text,
        key_recommendations=recs,
    )
