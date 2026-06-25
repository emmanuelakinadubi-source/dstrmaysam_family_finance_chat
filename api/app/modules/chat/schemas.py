from __future__ import annotations
import uuid
from typing import Optional
from pydantic import BaseModel


class MessageIn(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    session_id: Optional[uuid.UUID] = None
    message: str
    module: str = "family"  # family | company | vendor


class ChatResponse(BaseModel):
    session_id: uuid.UUID
    answer: str
    model_used: Optional[str]
    latency_ms: Optional[float]
    tokens_used: Optional[int]


class SessionOut(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    module: str

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model_used: Optional[str]
    latency_ms: Optional[float]

    class Config:
        from_attributes = True
