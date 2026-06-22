import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import settings
from app.tools.chromadb_storage import collection_count, get_vectorstore, reset_collection
from app.tools.chunking import chunk_venue
from app.tools.venue_fetch import fetch_venues

logger = logging.getLogger(__name__)


def _metadata_path() -> str:
    return os.path.join(settings.chroma_persist_dir, "indexing_metadata.json")


def _venue_hash(venue: Dict) -> str:
    key = "|".join([
        str(venue.get("name", "")),
        str(venue.get("city", "")),
        str(venue.get("max_capacity", 0)),
        str(venue.get("min_price", 0)),
        str(venue.get("max_price", 0)),
    ])
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _get_indexed_hashes() -> Dict[str, str]:
    """Returns {venue_id: content_hash} for all chunks in the collection."""
    try:
        vs = get_vectorstore()
        results = vs._collection.get(include=["metadatas"])
        hashes: Dict[str, str] = {}
        for meta in results.get("metadatas", []):
            vid = meta.get("venue_id", "")
            h = meta.get("content_hash", "")
            if vid and vid not in hashes:
                hashes[vid] = h
        return hashes
    except Exception as exc:
        logger.error("Could not read indexed hashes: %s", exc)
        return {}


def _delete_venue_chunks(venue_id: str) -> None:
    try:
        vs = get_vectorstore()
        results = vs._collection.get(where={"venue_id": {"$eq": venue_id}})
        if results.get("ids"):
            vs._collection.delete(ids=results["ids"])
    except Exception as exc:
        logger.warning("Could not delete chunks for venue %s: %s", venue_id, exc)


def _index_venues(venues_to_add: list) -> int:
    vs = get_vectorstore()
    total_chunks = 0
    for venue in venues_to_add:
        h = _venue_hash(venue)
        chunks = chunk_venue(venue)
        for chunk in chunks:
            chunk["metadata"]["content_hash"] = h
        try:
            vs.add_texts(
                texts=[c["text"] for c in chunks],
                metadatas=[c["metadata"] for c in chunks],
                ids=[c["id"] for c in chunks],
            )
            total_chunks += len(chunks)
        except Exception as exc:
            logger.error("Failed to index venue %s: %s", venue.get("venue_id"), exc)
    return total_chunks


def run_incremental_indexing() -> Dict[str, Any]:
    """Fetch Canvas API, detect changes, apply incremental updates to venue_master."""
    logger.info("Starting incremental venue indexing")

    venues = fetch_venues()
    if not venues:
        msg = "Failed to fetch venues from Canvas API"
        logger.error(msg)
        return {"error": msg, "status": "failed"}

    indexed = _get_indexed_hashes()
    fetched_map = {v["venue_id"]: v for v in venues}

    new_ids = set(fetched_map) - set(indexed)
    removed_ids = set(indexed) - set(fetched_map)
    updated_ids = {
        vid
        for vid in (set(fetched_map) & set(indexed))
        if _venue_hash(fetched_map[vid]) != indexed[vid]
    }

    # Remove deleted venues
    for vid in removed_ids:
        _delete_venue_chunks(vid)

    # Remove old chunks for updated venues before re-adding
    for vid in updated_ids:
        _delete_venue_chunks(vid)

    to_add = [fetched_map[vid] for vid in (new_ids | updated_ids)]
    _index_venues(to_add)

    metadata = {
        "last_indexed_at": datetime.now(timezone.utc).isoformat(),
        "total_venues": len(venues),
        "new_venues": len(new_ids),
        "updated_venues": len(updated_ids),
        "removed_venues": len(removed_ids),
        "total_chunks": collection_count(),
        "status": "ok",
    }
    _save_metadata(metadata)
    logger.info(
        "Indexing complete: %d new, %d updated, %d removed", len(new_ids), len(updated_ids), len(removed_ids)
    )
    return metadata


def run_full_reindex() -> Dict[str, Any]:
    """Wipe and rebuild the entire venue_master collection."""
    logger.info("Starting full venue re-index")
    reset_collection()
    venues = fetch_venues()
    if not venues:
        return {"error": "Failed to fetch venues", "status": "failed"}
    _index_venues(venues)
    metadata = {
        "last_indexed_at": datetime.now(timezone.utc).isoformat(),
        "total_venues": len(venues),
        "new_venues": len(venues),
        "updated_venues": 0,
        "removed_venues": 0,
        "total_chunks": collection_count(),
        "status": "ok",
    }
    _save_metadata(metadata)
    return metadata


def load_metadata() -> Dict[str, Any]:
    path = _metadata_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_indexed_at": None,
        "total_venues": 0,
        "new_venues": 0,
        "updated_venues": 0,
        "removed_venues": 0,
        "total_chunks": collection_count(),
        "status": "not_indexed",
    }


def _save_metadata(metadata: Dict) -> None:
    path = _metadata_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(metadata, f, indent=2)
    except Exception as exc:
        logger.error("Could not save indexing metadata: %s", exc)
