import logging

from fastapi import APIRouter, HTTPException

from app.services.indexing_service import load_metadata, run_full_reindex, run_incremental_indexing
from app.services.scheduler import get_next_run_time
from app.tools.chromadb_storage import collection_count, get_vectorstore

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/index/reindex")
async def trigger_reindex(full: bool = False):
    """Trigger manual venue reindex. full=true wipes and rebuilds from scratch."""
    logger.info("Manual reindex triggered (full=%s)", full)
    if full:
        result = run_full_reindex()
    else:
        result = run_incremental_indexing()
    if result.get("status") == "failed":
        raise HTTPException(status_code=502, detail=result.get("error", "Reindex failed"))
    return result


@router.get("/index/stats")
async def get_stats():
    """Return venue database statistics and indexing metadata."""
    meta = load_metadata()
    meta["live_chunk_count"] = collection_count()
    try:
        meta["next_scheduled_indexing"] = get_next_run_time()
    except Exception:
        meta["next_scheduled_indexing"] = "unknown"
    return meta


@router.get("/index/health")
async def health_check():
    """Check ChromaDB collection health."""
    try:
        vs = get_vectorstore()
        count = vs._collection.count()
        meta = load_metadata()
        return {
            "status": "healthy" if count > 0 else "empty",
            "collection_name": "venue_master",
            "chunk_count": count,
            "last_indexed_at": meta.get("last_indexed_at"),
            "total_venues": meta.get("total_venues", 0),
        }
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Collection health check failed: {exc}")
