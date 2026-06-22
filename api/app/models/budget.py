from sqlalchemy import Column, String, Float, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import UUIDBase

EXPENSE_CATEGORIES = [
    "Groceries", "Wears", "Car Loan", "House Rent",
    "Entertainment", "Gift", "Host Visitors", "Travel", "Miscellaneous",
]

ALLOCATION_DEFAULTS = {
    "expenses": 0.40,
    "family_savings": 0.20,
    "personal_savings": 0.20,
    "emergency_fund": 0.10,
    "tithe": 0.10,
}

ADJUSTMENT_PRIORITY = ["tithe", "expenses", "family_savings", "emergency_fund", "personal_savings"]


class MonthlyBudget(UUIDBase):
    __tablename__ = "monthly_budgets"

    household_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    month = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    husband_income = Column(Float, default=0.0, nullable=False)
    wife_income = Column(Float, default=0.0, nullable=False)
    total_income = Column(Float, default=0.0, nullable=False)
    notes = Column(String(500), nullable=True)

    allocations = relationship("BudgetAllocation", back_populates="budget", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="budget", cascade="all, delete-orphan")
    savings = relationship("Saving", back_populates="budget", cascade="all, delete-orphan")


class BudgetAllocation(UUIDBase):
    __tablename__ = "budget_allocations"

    budget_id = Column(UUID(as_uuid=True), ForeignKey("monthly_budgets.id"), nullable=False)
    category = Column(String(50), nullable=False)
    percentage = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    husband_amount = Column(Float, nullable=False)
    wife_amount = Column(Float, nullable=False)

    budget = relationship("MonthlyBudget", back_populates="allocations")


class Expense(UUIDBase):
    __tablename__ = "expenses"

    budget_id = Column(UUID(as_uuid=True), ForeignKey("monthly_budgets.id"), nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(300), nullable=True)
    vendor = Column(String(150), nullable=True)

    budget = relationship("MonthlyBudget", back_populates="expenses")


class Saving(UUIDBase):
    __tablename__ = "savings"

    budget_id = Column(UUID(as_uuid=True), ForeignKey("monthly_budgets.id"), nullable=False)
    saving_type = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)

    budget = relationship("MonthlyBudget", back_populates="savings")


# ── Company Budget Models ──────────────────────────────────────────────────────

class CompanyBudget(UUIDBase):
    __tablename__ = "company_budgets"

    title = Column(String(200), nullable=False)
    department = Column(String(100), nullable=True)
    total_budget = Column(Float, nullable=False)
    period_start = Column(String(20), nullable=True)
    period_end = Column(String(20), nullable=True)
    status = Column(String(50), default="draft", nullable=False)
    extracted_data = Column(JSON, nullable=True)
    notes = Column(String(500), nullable=True)

    items = relationship("BudgetItem", back_populates="budget", cascade="all, delete-orphan")


class BudgetItem(UUIDBase):
    __tablename__ = "budget_items"

    budget_id = Column(UUID(as_uuid=True), ForeignKey("company_budgets.id"), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    estimated_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, nullable=True)

    budget = relationship("CompanyBudget", back_populates="items")
