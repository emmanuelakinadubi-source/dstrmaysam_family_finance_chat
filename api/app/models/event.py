from sqlalchemy import Column, String, Float, Integer, ForeignKey, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import UUIDBase


class EventPlan(UUIDBase):
    __tablename__ = "event_plans"

    # Core MVP fields
    event_name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=True, index=True)
    event_date = Column(String(50), nullable=True)   # stored as string from LLM extraction
    event_time = Column(String(20), nullable=True)   # "09:00"
    attendee_count = Column(Integer, nullable=True)
    number_of_days = Column(Integer, default=1, nullable=True)
    food_required = Column(Boolean, default=False, nullable=True)
    hosting_required = Column(Boolean, default=False, nullable=True)
    budget = Column(Float, nullable=True)

    # Extended fields (Phase 2)
    venue = Column(String(200), nullable=True)
    hotel = Column(String(200), nullable=True)
    food_requirements = Column(String(500), nullable=True)
    welfare_budget = Column(Float, nullable=True)
    special_requirements = Column(String(500), nullable=True)
    location = Column(String(200), nullable=True)

    status = Column(String(50), default="draft", nullable=False)
    extracted_data = Column(JSON, nullable=True)

    vendor_matches = relationship("EventVendor", back_populates="event", cascade="all, delete-orphan")


class EventVendor(UUIDBase):
    __tablename__ = "event_vendors"

    event_id = Column(UUID(as_uuid=True), ForeignKey("event_plans.id"), nullable=False)
    vendor_name = Column(String(150), nullable=False)
    vendor_type = Column(String(50), nullable=False)
    estimated_cost = Column(Float, nullable=True)
    fit_score = Column(Float, nullable=True)
    rank = Column(Integer, nullable=True)
    notes = Column(String(300), nullable=True)

    event = relationship("EventPlan", back_populates="vendor_matches")
