"""Agent 2 – Venue Retrieval Agent.

Builds a semantic query from extracted requirements and retrieves the top-k
relevant venue chunks from ChromaDB.
"""
from typing import Any, Dict, List

from app.schemas.event import EventRequirements
from app.tools.retrieval import retrieve_venues


def retrieve_for_requirements(requirements: EventRequirements) -> List[Dict[str, Any]]:
    query = _build_query(requirements)
    return retrieve_venues(query=query, city=requirements.city, top_k=10)


def _build_query(requirements: EventRequirements) -> str:
    parts: List[str] = []
    if requirements.city:
        parts.append(f"venue in {requirements.city}")
    if requirements.attendees > 0:
        parts.append(f"capacity for {requirements.attendees} guests")
    if requirements.max_budget > 0:
        parts.append(f"budget up to £{requirements.max_budget:,.0f}")
    if requirements.additional_requirements:
        parts.extend(requirements.additional_requirements[:3])
    return " ".join(parts) if parts else "event venue corporate"
