from sqlalchemy import Column, String, Text, Integer
from app.db.base import UUIDBase


class EventDraft(UUIDBase):
    """
    Persists a submitted event brief so the user can reload it without re-uploading.
    Stores the original filename, extracted requirements JSON, venue results JSON,
    and the ChromaDB collection name so the chat agent can reference it directly.
    """
    __tablename__ = "event_drafts"

    filename          = Column(String(255), nullable=False)
    event_name        = Column(String(255), nullable=True)
    city              = Column(String(100), nullable=True)
    postcode          = Column(String(20),  nullable=True)
    event_date        = Column(String(50),  nullable=True)
    attendees         = Column(Integer,     nullable=True)
    max_budget        = Column(String(50),  nullable=True)
    event_collection  = Column(String(100), nullable=True)     # ChromaDB collection
    event_id          = Column(String(36),  nullable=True)     # FK to event_plans
    requirements_json = Column(Text,        nullable=True)     # full EventRequirements JSON
    venues_json       = Column(Text,        nullable=True)     # recommended_venues JSON
    summary_json      = Column(Text,        nullable=True)     # RecommendationSummary JSON
    agent_response    = Column(Text,        nullable=True)
