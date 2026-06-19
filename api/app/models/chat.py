from sqlalchemy import Column, String, Text, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import UUIDBase


class ChatSession(UUIDBase):
    __tablename__ = "chat_sessions"

    title = Column(String(200), nullable=True)
    module = Column(String(50), nullable=False, default="family")  # family | company | vendor

    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan",
                            order_by="ChatMessage.created_at")


class ChatMessage(UUIDBase):
    __tablename__ = "chat_messages"

    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False)
    tokens_used = Column(Integer, nullable=True)
    model_used = Column(String(100), nullable=True)
    latency_ms = Column(Float, nullable=True)

    session = relationship("ChatSession", back_populates="messages")
