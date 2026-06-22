import json
import logging

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from app.services.indexing_service import load_metadata
from app.services.scheduler import get_next_run_time
from app.tools.chromadb_storage import collection_count

logger = logging.getLogger(__name__)


class CollectionStatsInput(BaseModel):
    pass


def _stats_fn() -> str:
    """Return current indexing status and collection health."""
    try:
        meta = load_metadata()
        live_count = collection_count()
        meta["live_chunk_count"] = live_count
        try:
            meta["next_scheduled_indexing"] = get_next_run_time()
        except Exception:
            meta["next_scheduled_indexing"] = "unknown"
        meta["collection_name"] = "venue_master"
        meta["health"] = "healthy" if live_count > 0 else "empty"
        return json.dumps(meta)
    except Exception as exc:
        logger.error("Collection stats failed: %s", exc)
        return json.dumps({"error": str(exc), "health": "unknown"})


get_collection_stats = StructuredTool.from_function(
    func=_stats_fn,
    name="get_collection_stats",
    description=(
        "Get the current status of the venue_master ChromaDB collection. "
        "Returns: last indexed timestamp, total venues, new/updated/removed counts, "
        "total chunks, collection health, and next scheduled indexing time. "
        "Use this when the user asks about the venue database or indexing status."
    ),
    args_schema=CollectionStatsInput,
)
