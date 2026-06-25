import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.retrieval import retrieve_venues

logger = logging.getLogger(__name__)


class VenueRetrievalInput(BaseModel):
    query: str = Field(description="Natural language search query describing venue requirements")
    city: str = Field(default="", description="City to filter results (empty for nationwide search)")
    top_k: int = Field(default=15, description="Maximum number of venue chunks to retrieve")


def _search_fn(query: str, city: str = "", top_k: int = 15) -> str:
    try:
        chunks = retrieve_venues(
            query=query,
            city=city.strip() if city and city.strip() else None,
            top_k=top_k,
        )
        results = []
        for c in chunks:
            meta = c.get("metadata", {})
            results.append({
                "venue_id": meta.get("venue_id", ""),
                "venue_name": meta.get("venue_name", ""),
                "city": meta.get("city", ""),
                "capacity": meta.get("capacity", "0"),
                "min_price": meta.get("min_price", "0"),
                "max_price": meta.get("max_price", "0"),
                "relevance_score": round(c.get("relevance_score", 0.0), 3),
                "snippet": c.get("text", "")[:300],
            })
        return json.dumps({"results": results, "count": len(results)})
    except Exception as exc:
        logger.error("Venue retrieval failed: %s", exc)
        return json.dumps({"results": [], "count": 0, "error": str(exc)})


search_venues = StructuredTool.from_function(
    func=_search_fn,
    name="search_venues",
    description=(
        "Search the venue_master knowledge base for venues matching a natural language query. "
        "Use this to answer specific questions about venue features, pricing, location, parking, AV, etc. "
        "Returns a list of matching venue chunks with metadata and relevance scores."
    ),
    args_schema=VenueRetrievalInput,
)
