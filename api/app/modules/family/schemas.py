from __future__ import annotations
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field


class IncomeInput(BaseModel):
    month: str
    year: int
    husband_income: float = Field(ge=0)
    wife_income: float = Field(ge=0)
    notes: Optional[str] = None


class AllocationResult(BaseModel):
    category: str
    percentage: float
    total_amount: float
    husband_amount: float
    wife_amount: float


class BudgetCalculation(BaseModel):
    total_income: float
    husband_income: float
    wife_income: float
    husband_percentage: float
    wife_percentage: float
    allocations: List[AllocationResult]
    deficit: Optional[float] = None
    recommendations: Optional[List[str]] = None


class ExpenseCreate(BaseModel):
    category: str
    amount: float = Field(ge=0)
    description: Optional[str] = None
    vendor: Optional[str] = None


class ExpenseOut(ExpenseCreate):
    id: uuid.UUID
    budget_id: uuid.UUID

    class Config:
        from_attributes = True


class BudgetCreate(BaseModel):
    month: str
    year: int
    husband_income: float = Field(ge=0)
    wife_income: float = Field(ge=0)
    expenses: Optional[List[ExpenseCreate]] = []
    notes: Optional[str] = None


class BudgetOut(BaseModel):
    id: uuid.UUID
    month: str
    year: int
    husband_income: float
    wife_income: float
    total_income: float
    notes: Optional[str]
    expenses: List[ExpenseOut] = []

    class Config:
        from_attributes = True
