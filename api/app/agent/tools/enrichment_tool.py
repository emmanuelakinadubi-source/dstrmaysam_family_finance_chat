import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.tools.chromadb_storage import get_vectorstore

logger = logging.getLogger(__name__)


class EnrichmentInput(BaseModel):
    venue_id: str = Field(description="The unique venue ID to retrieve full operational details for")


def _enrich_fn(venue_id: str) -> str:
    """Look up a venue's full details from ChromaDB metadata."""
    try:
        vs = get_vectorstore()
        results = vs._collection.get(
            where={"venue_id": {"$eq": venue_id}},
            include=["metadatas", "documents"],
        )
        metadatas = results.get("metadatas", [])
        documents = results.get("documents", [])
        if not metadatas:
            return json.dumps({"error": f"Venue '{venue_id}' not found in collection"})

        meta = metadatas[0]
        full_text = " ".join(documents[:3]) if documents else ""

        details = {
            "venue_id": meta.get("venue_id", venue_id),
            "venue_name": meta.get("venue_name", "Unknown"),
            "city": meta.get("city", ""),
            "postcode": meta.get("postcode", ""),
            "capacity": meta.get("capacity", "0"),
            "price_range": f"£{meta.get('min_price', '0')} – £{meta.get('max_price', '0')}",
            "venue_url": meta.get("venue_url", ""),
            "features": [f.strip() for f in (meta.get("features") or "").split(",") if f.strip()],
            "event_types": [t.strip() for t in (meta.get("event_types") or "").split(",") if t.strip()],
            # Transport & accessibility
            "parking": meta.get("parking", ""),
            "nearest_parking": meta.get("nearest_parking", ""),
            "public_transport": meta.get("public_transport", ""),
            "nearest_train": meta.get("nearest_train", ""),
            "nearest_underground": meta.get("nearest_underground", ""),
            "wheelchair_access": meta.get("wheelchair_access", ""),
            # Technology & facilities
            "wifi": meta.get("wifi", ""),
            "av_equipment": meta.get("av_equipment", ""),
            "hybrid_events": meta.get("hybrid_events", ""),
            "live_streaming": meta.get("live_streaming", ""),
            # Catering & hospitality
            "catering": meta.get("catering", ""),
            "alcohol_license": meta.get("alcohol_license", ""),
            "accommodation": meta.get("accommodation", ""),
            "outdoor_space": meta.get("outdoor_space", ""),
            "sustainability": meta.get("sustainability", ""),
            # Business metrics
            "response_rate": meta.get("response_rate", ""),
            "response_time": meta.get("response_time", ""),
            "full_description": full_text[:600],
        }
        return json.dumps(details)
    except Exception as exc:
        logger.error("Enrichment failed for venue %s: %s", venue_id, exc)
        return json.dumps({"error": str(exc), "venue_id": venue_id})


enrich_venue_details = StructuredTool.from_function(
    func=_enrich_fn,
    name="enrich_venue_details",
    description=(
        "Retrieve full operational details for a specific venue by its ID. "
        "Returns comprehensive information including parking, transport, AV, catering, accessibility, "
        "sustainability, and response metrics. Use this when a user asks about a specific venue's amenities."
    ),
    args_schema=EnrichmentInput,
)
