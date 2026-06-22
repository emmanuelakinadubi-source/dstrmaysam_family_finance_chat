"""Agent 3 – Venue Ranking Agent.

Scores and ranks retrieved venue chunks against the event requirements.
"""
from typing import Any, Dict, List

from app.schemas.event import EventRequirements
from app.tools.ranking import rank_venues


def rank_for_requirements(
    chunks: List[Dict[str, Any]],
    requirements: EventRequirements,
) -> List[Dict[str, Any]]:
    return rank_venues(chunks, requirements)
