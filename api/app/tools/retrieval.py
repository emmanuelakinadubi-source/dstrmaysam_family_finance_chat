from typing import Any, Dict, List, Optional

from app.tools.chromadb_storage import get_vectorstore


def retrieve_venues(
    query: str,
    city: Optional[str] = None,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    vs = get_vectorstore()
    where_filter = None
    if city and city.strip():
        where_filter = {"city": {"$eq": city.strip()}}

    try:
        if where_filter:
            docs_scores = vs.similarity_search_with_score(query, k=top_k, filter=where_filter)
        else:
            docs_scores = vs.similarity_search_with_score(query, k=top_k)
    except Exception:
        # Fall back without filter if metadata filter fails (empty collection, etc.)
        docs_scores = vs.similarity_search_with_score(query, k=top_k)

    results = []
    for doc, score in docs_scores:
        # Chroma cosine distance: 0 = identical. Convert to 0-1 similarity.
        similarity = max(0.0, 1.0 - float(score))
        results.append({
            "text": doc.page_content,
            "metadata": doc.metadata,
            "relevance_score": similarity,
        })

    return results
