import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

_COLLECTION_MAP = {
    "family": settings.chroma_collection_family,
    "company": settings.chroma_collection_company,
    "vendor": settings.chroma_collection_family,
}


def retrieve_context(query: str, collection: str = "family", k: int = 4) -> Optional[str]:
    """Return top-k retrieved chunks as a single context string, or None on failure."""
    try:
        from app.modules.rag.pipeline import get_vector_store
        collection_name = _COLLECTION_MAP.get(collection, settings.chroma_collection_family)
        store = get_vector_store(collection_name)
        docs = store.similarity_search(query, k=k)
        if not docs:
            return None
        return "\n\n".join(d.page_content for d in docs)
    except Exception as e:
        logger.warning("RAG retrieval failed (continuing without context): %s", e)
        return None
