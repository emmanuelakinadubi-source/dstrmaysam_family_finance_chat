import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.event_storage import retrieve_event_requirements

logger = logging.getLogger(__name__)


class EventQueryInput(BaseModel):
    query: str = Field(description="Natural language question about the user's event requirements")
    collection: str = Field(
        default="event_management",
        description="Collection to query: 'event_management' (default) or 'event_request_<id>'",
    )


def _query_event_fn(query: str, collection: str = "event_management") -> str:
    try:
        chunks = retrieve_event_requirements(query, collection_name=collection, top_k=6)
        if not chunks:
            return json.dumps({
                "results": [],
                "count": 0,
                "collection": collection,
                "message": (
                    "No event requirements found in this collection. "
                    "Please go to Corporate Event Management and upload your event brief first."
                ),
            })

        results = []
        for c in chunks:
            meta = c.get("metadata", {})
            results.append({
                "city": meta.get("city", ""),
                "attendees": meta.get("attendees", "0"),
                "min_budget": meta.get("min_budget", "0"),
                "max_budget": meta.get("max_budget", "0"),
                "event_date": meta.get("event_date", ""),
                "additional_requirements": meta.get("additional_requirements", ""),
                "event_id": meta.get("event_id", ""),
                "relevance_score": round(c.get("relevance_score", 0.0), 3),
                "snippet": c.get("text", "")[:400],
            })

        return json.dumps({"results": results, "count": len(results), "collection": collection})
    except Exception as exc:
        logger.error("Event query tool failed: %s", exc)
        return json.dumps({"results": [], "count": 0, "error": str(exc)})


search_event_requirements = StructuredTool.from_function(
    func=_query_event_fn,
    name="search_event_requirements",
    description=(
        "Search the event requirements knowledge base to retrieve details about the user's event. "
        "Use this when knowledge_source is 'event_management' or 'event_request_*'. "
        "Returns: city, attendees, budget, date, additional requirements from the indexed event brief. "
        "If results are empty, inform the user to upload requirements via Corporate Event Management. "
        "After retrieving event requirements, call recommend_venues or find_nearby_venues for venue matching."
    ),
    args_schema=EventQueryInput,
)
