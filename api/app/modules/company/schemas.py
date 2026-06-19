from __future__ import annotations
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field


class BudgetItemCreate(BaseModel):
    category: str
    description: Optional[str] = None
    estimated_amount: float = Field(ge=0)
    actual_amount: Optional[float] = None


class CompanyBudgetCreate(BaseModel):
    title: str
    department: Optional[str] = None
    total_budget: float = Field(ge=0)
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    notes: Optional[str] = None
    items: Optional[List[BudgetItemCreate]] = []


class BudgetItemOut(BudgetItemCreate):
    id: uuid.UUID
    budget_id: uuid.UUID

    class Config:
        from_attributes = True


class CompanyBudgetOut(BaseModel):
    id: uuid.UUID
    title: str
    department: Optional[str]
    total_budget: float
    period_start: Optional[str]
    period_end: Optional[str]
    status: str
    notes: Optional[str]
    items: List[BudgetItemOut] = []

    class Config:
        from_attributes = True


class EventPlanCreate(BaseModel):
    event_name: str
    event_date: Optional[str] = None
    attendee_count: Optional[int] = None
    budget: Optional[float] = None
    venue: Optional[str] = None
    hotel: Optional[str] = None
    food_requirements: Optional[str] = None
    welfare_budget: Optional[float] = None
    special_requirements: Optional[str] = None
    location: Optional[str] = None


class EventPlanOut(EventPlanCreate):
    id: uuid.UUID
    status: str

    class Config:
        from_attributes = True


class VendorMatchResult(BaseModel):
    vendor_name: str
    vendor_type: str
    estimated_cost: float
    fit_score: float
    rank: int
    notes: Optional[str] = None
