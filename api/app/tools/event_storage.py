import logging
import time
from typing import Any, Dict, List

from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.tools.embedding import get_embeddings

logger = logging.getLogger(__name__)

_event_stores: Dict[str, Chroma] = {}


def get_event_vectorstore(collection_name: str = "event_management") -> Chroma:
    if collection_name not in _event_stores:
        _event_stores[collection_name] = Chroma(
            collection_name=collection_name,
            embedding_function=get_embeddings(),
            persist_directory=settings.chroma_persist_dir,
        )
    return _event_stores[collection_name]


def store_event_requirements(
    raw_text: str,
    requirements: Dict[str, Any],
    collection_name: str = "event_management",
) -> str:
    """Chunk and store event requirements. Returns the collection name used."""
    event_id = f"evt_{int(time.time())}"

    def _safe_float(v) -> float:
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    structured_text = (
        "Event Requirements Summary:\n"
        f"City: {requirements.get('city', '')}\n"
        f"Event Date: {requirements.get('event_date', '')}\n"
        f"Event Time: {requirements.get('event_time', '')}\n"
        f"Attendees: {requirements.get('attendees', 0)}\n"
        f"Budget: £{_safe_float(requirements.get('min_budget')):,.0f}"
        f" – £{_safe_float(requirements.get('max_budget')):,.0f}\n"
        f"Additional Requirements: {', '.join(requirements.get('additional_requirements', []))}\n\n"
        f"Full Submission:\n{raw_text[:3000]}"
    )

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
    chunks = splitter.split_text(structured_text)

    metadata = {
        "source": "event_upload",
        "event_id": event_id,
        "city": str(requirements.get("city", "")),
        "attendees": str(requirements.get("attendees", 0)),
        "min_budget": str(_safe_float(requirements.get("min_budget"))),
        "max_budget": str(_safe_float(requirements.get("max_budget"))),
        "event_date": str(requirements.get("event_date", "")),
        "additional_requirements": ", ".join(requirements.get("additional_requirements", [])),
    }

    vs = get_event_vectorstore(collection_name)
    try:
        vs.add_texts(
            texts=chunks,
            metadatas=[{**metadata} for _ in chunks],
            ids=[f"{event_id}_{i}" for i in range(len(chunks))],
        )
        logger.info("Stored event '%s' in '%s' (%d chunks)", event_id, collection_name, len(chunks))
    except Exception as exc:
        logger.error("Failed to store event requirements: %s", exc)

    return collection_name


def retrieve_event_requirements(
    query: str,
    collection_name: str = "event_management",
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    try:
        vs = get_event_vectorstore(collection_name)
        docs_scores = vs.similarity_search_with_score(query, k=top_k)
    except Exception as exc:
        logger.error("Event retrieval failed for '%s': %s", collection_name, exc)
        return []

    results = []
    for doc, score in docs_scores:
        similarity = max(0.0, 1.0 - float(score))
        results.append({
            "text": doc.page_content,
            "metadata": doc.metadata,
            "relevance_score": similarity,
        })
    return results


def event_collection_count(collection_name: str = "event_management") -> int:
    try:
        return get_event_vectorstore(collection_name)._collection.count()
    except Exception:
        return 0
