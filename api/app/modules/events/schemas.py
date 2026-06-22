from __future__ import annotations
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field


class EventExtractionOutput(BaseModel):
    """Structured output schema used by the extraction agent."""
    event_name: str = Field(description="Name of the event")
    city: Optional[str] = Field(None, description="City where the event takes place")
    event_date: Optional[str] = Field(None, description="Date of the event (YYYY-MM-DD or human-readable)")
    event_time: Optional[str] = Field(None, description="Start time of the event (HH:MM)")
    attendee_count: Optional[int] = Field(None, description="Number of attendees")
    number_of_days: Optional[int] = Field(None, description="Duration of the event in days")
    food_required: Optional[bool] = Field(None, description="Whether catering/food is required")
    hosting_required: Optional[bool] = Field(None, description="Whether hotel/accommodation is required")
    budget: Optional[float] = Field(None, description="Total event budget in GBP as a numeric value")


class EventPlanOut(BaseModel):
    id: uuid.UUID
    event_name: str
    city: Optional[str]
    event_date: Optional[str]
    event_time: Optional[str]
    attendee_count: Optional[int]
    number_of_days: Optional[int]
    food_required: Optional[bool]
    hosting_required: Optional[bool]
    budget: Optional[float]
    status: str
    extracted_data: Optional[dict]

    class Config:
        from_attributes = True


class VendorMatchOut(BaseModel):
    vendor_name: str
    vendor_type: str
    city: str
    price_per_person: float
    estimated_cost: float
    budget_remaining: float
    fit_score: float
    city_match: bool
    rank: int


class VendorRecommendationsOut(BaseModel):
    event_id: uuid.UUID
    event_name: str
    budget: float
    best_match: Optional[VendorMatchOut]
    cheapest_match: Optional[VendorMatchOut]
    closest_match: Optional[VendorMatchOut]
    all_matches: List[VendorMatchOut]
