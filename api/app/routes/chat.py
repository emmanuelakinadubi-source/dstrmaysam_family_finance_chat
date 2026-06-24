from fastapi import APIRouter, HTTPException

from app.agent.event_agent import chat_with_agent
from app.schemas.event import ChatRequest, ChatResponse
from app.tools.guardrails import check_prompt_injection

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    if check_prompt_injection(request.message):
        raise HTTPException(status_code=400, detail="Message contains disallowed content.")

    history = [{"role": m.role, "content": m.content} for m in (request.history or [])]

    # Prepend event context block so agent knows about the uploaded draft
    message = request.message
    if request.event_context:
        message = f"{request.event_context}\n\nUser question: {request.message}"

    result = chat_with_agent(
        message=message,
        knowledge_source=request.knowledge_source or "venue_master",
        history=history,
    )
    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        knowledge_source=result.get("knowledge_source", request.knowledge_source),
    )
