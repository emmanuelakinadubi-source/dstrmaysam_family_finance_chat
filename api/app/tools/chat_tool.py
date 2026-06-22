import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an Event Planning AI Assistant specialising in venue recommendations.

Rules:
1. Answer questions using ONLY the venue context provided below.
2. Never invent venue names, prices, capacities, or features.
3. Cite specific venue attributes when making claims.
4. If the answer is not in the context, say "I don't have that information in the current venue data."
5. Be concise and helpful."""


def answer_venue_question(
    message: str,
    venue_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not venue_chunks:
        return {
            "answer": "No venue data is loaded yet. Please submit event requirements first so I can retrieve relevant venues.",
            "sources": [],
        }

    context = _build_context(venue_chunks)
    sources = list({c.get("metadata", {}).get("venue_name", "Unknown") for c in venue_chunks})

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Venue Context:\n{context}\n\nQuestion: {message}"),
    ]
    try:
        response = _get_llm().invoke(messages)
        return {"answer": response.content.strip(), "sources": sources}
    except Exception as exc:
        logger.error("Chat LLM call failed: %s", exc)
        return {"answer": "I encountered an error. Please try again.", "sources": []}


def _build_context(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for chunk in chunks[:8]:
        name = chunk.get("metadata", {}).get("venue_name", "Unknown")
        parts.append(f"[{name}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.3,
    )
