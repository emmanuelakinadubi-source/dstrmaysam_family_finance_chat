import logging
from typing import Any, Dict, List, Optional

from langchain_community.vectorstores import Chroma

from app.core.config import settings
from app.tools.embedding import get_embeddings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "venue_master"

_vectorstore: Optional[Chroma] = None


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=get_embeddings(),
            persist_directory=settings.chroma_persist_dir,
        )
    return _vectorstore


def store_chunks(chunks: List[Dict[str, Any]]) -> None:
    if not chunks:
        return
    vs = get_vectorstore()
    try:
        vs.add_texts(
            texts=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
            ids=[c["id"] for c in chunks],
        )
        logger.info("Stored %d chunks in ChromaDB", len(chunks))
    except Exception as exc:
        logger.error("ChromaDB store failed: %s", exc)


def collection_count() -> int:
    try:
        return get_vectorstore()._collection.count()
    except Exception:
        return 0


def reset_collection() -> None:
    global _vectorstore
    try:
        vs = get_vectorstore()
        vs._client.delete_collection(COLLECTION_NAME)
        _vectorstore = None
        logger.info("ChromaDB collection '%s' reset", COLLECTION_NAME)
    except Exception as exc:
        logger.error("ChromaDB reset failed: %s", exc)
