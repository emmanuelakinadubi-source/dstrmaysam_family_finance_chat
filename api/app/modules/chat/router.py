import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.chat import ChatSession, ChatMessage
from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionOut, MessageOut
from app.modules.chat.llm import chat_with_llm
from app.modules.rag.retriever import retrieve_context

router = APIRouter(prefix="/chat", tags=["Chat"])


def _get_or_create_session(db: Session, session_id: uuid.UUID | None, module: str) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if session:
            return session
    session = ChatSession(module=module)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/", response_model=ChatResponse)
def chat(data: ChatRequest, db: Session = Depends(get_db)):
    session = _get_or_create_session(db, data.session_id, data.module)

    history = [
        {"role": m.role, "content": m.content}
        for m in session.messages[-10:]  # last 10 messages for context window
    ]

    context = retrieve_context(data.message, collection=data.module)

    history.append({"role": "user", "content": data.message})
    result = chat_with_llm(history, module=data.module, context=context)

    db.add(ChatMessage(session_id=session.id, role="user", content=data.message))
    db.add(ChatMessage(
        session_id=session.id,
        role="assistant",
        content=result["content"],
        model_used=result["model_used"],
        latency_ms=result["latency_ms"],
        tokens_used=result["tokens_used"],
    ))
    db.commit()

    return ChatResponse(
        session_id=session.id,
        answer=result["content"],
        model_used=result["model_used"],
        latency_ms=result["latency_ms"],
        tokens_used=result["tokens_used"],
    )


@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(ChatSession).filter(ChatSession.deleted_at.is_(None)).all()


@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_messages(session_id: uuid.UUID, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.messages
