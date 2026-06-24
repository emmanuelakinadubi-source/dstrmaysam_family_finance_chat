"""
RAG indexing of scraped vendor data into ChromaDB.

Collection: 'vendor_intel'
Each vendor → one rich-text document + structured metadata.
Indexed documents are immediately queryable by the chat agent.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.modules.vendors.smart_scraper import ScrapedVendor

logger = logging.getLogger(__name__)

VENDOR_COLLECTION = "vendor_intel"


# ── Text serialisation ────────────────────────────────────────────────────────

def _vendor_to_text(v: ScrapedVendor) -> str:
    """
    Convert a ScrapedVendor into a natural-language document for embedding.
    Richer text → better semantic retrieval.
    """
    lines = [
        f"{v.vendor_type.title()}: {v.name}",
    ]
    if v.address:
        lines.append(f"Address: {v.address}")
    if v.postcode:
        lines.append(f"Postcode: {v.postcode}")
    if v.distance_km:
        lines.append(f"Distance from event: {v.distance_km:.1f} km")
    if v.cuisine:
        lines.append(f"Cuisine / type: {v.cuisine}")
    if v.specializations:
        lines.append(f"Dietary options: {', '.join(v.specializations)}")
    if v.price_per_head is not None:
        lines.append(f"Estimated price per head: £{v.price_per_head:.2f}")
    if v.price_range:
        lines.append(f"Price range: {v.price_range}")
    if v.phone:
        lines.append(f"Phone: {v.phone}")
    if v.website:
        lines.append(f"Website: {v.website}")
    if v.opening_hours:
        lines.append(f"Opening hours: {v.opening_hours}")
    if v.rating is not None:
        lines.append(f"Rating: {v.rating:.1f}/5")
    if v.delivery_available:
        lines.append("Delivery: Yes — this vendor delivers to the event location")
    else:
        lines.append("Delivery: No — in-person / on-site only")
    if v.description:
        lines.append(f"About: {v.description}")
    lines.append(f"Data source: {v.source}")
    return "\n".join(lines)


def _vendor_metadata(v: ScrapedVendor, event_id: Optional[str]) -> dict:
    return {
        "vendor_type": v.vendor_type,
        "name": v.name,
        "distance_km": v.distance_km,
        "lat": v.lat,
        "lng": v.lng,
        "postcode": v.postcode or "",
        "cuisine": v.cuisine,
        "specializations": ",".join(v.specializations),
        "price_per_head": v.price_per_head or 0.0,
        "delivery_available": v.delivery_available,
        "source": v.source,
        "website": v.website or "",
        "phone": v.phone or "",
        "event_id": event_id or "",
    }


# ── ChromaDB helpers ──────────────────────────────────────────────────────────

def _get_vectorstore(collection: str):
    from langchain_community.vectorstores import Chroma
    from app.tools.embedding import get_embeddings
    from app.core.config import settings
    return Chroma(
        collection_name=collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def index_vendors(
    vendors: List[ScrapedVendor],
    event_id: Optional[str] = None,
) -> dict:
    """
    Embed and store vendor list in ChromaDB.

    Returns a summary dict: {"indexed": N, "collection": VENDOR_COLLECTION}
    """
    if not vendors:
        return {"indexed": 0, "collection": VENDOR_COLLECTION}

    texts     = [_vendor_to_text(v) for v in vendors]
    metadatas = [_vendor_metadata(v, event_id) for v in vendors]
    # Stable IDs prevent re-indexing duplicates on repeated scrapes
    ids = [
        f"{event_id or 'global'}_{v.vendor_type}_{v.osm_id or v.name[:20].replace(' ','_')}"
        for v in vendors
    ]

    try:
        vs = _get_vectorstore(VENDOR_COLLECTION)
        vs.add_texts(texts, metadatas=metadatas, ids=ids)
        logger.info("Indexed %d vendors into '%s'", len(vendors), VENDOR_COLLECTION)
        return {"indexed": len(vendors), "collection": VENDOR_COLLECTION}
    except Exception as exc:
        logger.error("Vendor indexing failed: %s", exc)
        return {"indexed": 0, "collection": VENDOR_COLLECTION, "error": str(exc)}


def search_vendor_intel(
    query: str,
    vendor_type: Optional[str] = None,
    event_id: Optional[str] = None,
    k: int = 8,
) -> List[dict]:
    """
    Semantic search over the vendor_intel ChromaDB collection.

    Optionally filter by vendor_type ("catering" | "hotel") and/or event_id.
    Returns list of dicts with 'content' + 'metadata'.
    """
    try:
        vs = _get_vectorstore(VENDOR_COLLECTION)

        where: dict = {}
        if vendor_type and event_id:
            where = {"$and": [{"vendor_type": vendor_type}, {"event_id": event_id}]}
        elif vendor_type:
            where = {"vendor_type": vendor_type}
        elif event_id:
            where = {"event_id": event_id}

        kwargs = {"k": k}
        if where:
            kwargs["filter"] = where

        docs = vs.similarity_search(query, **kwargs)
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]
    except Exception as exc:
        logger.warning("Vendor intel search failed: %s", exc)
        return []


def vendor_intel_count() -> int:
    """Number of documents currently in the vendor_intel collection."""
    try:
        vs = _get_vectorstore(VENDOR_COLLECTION)
        return vs._collection.count()
    except Exception:
        return 0
