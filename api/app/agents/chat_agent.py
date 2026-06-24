"""Agent 5 – Chat Agent.

Answers user questions about venues using RAG: retrieves relevant chunks
from ChromaDB then passes them as grounded context to the LLM. .....
"""
from typing import Any, Dict

from app.tools.chat_tool import answer_venue_question
from app.tools.retrieval import retrieve_venues


def chat(message: str) -> Dict[str, Any]:
    chunks = retrieve_venues(query=message, top_k=8)
    return answer_venue_question(message=message, venue_chunks=chunks)
