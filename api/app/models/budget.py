from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class MonthlyBudget(Base):
    __tablename__ = "monthly_budgets"

    id = Column(Integer, primary_key=True, index=True)
    month = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    husband_income = Column(Float, default=0.0)
    wife_income = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    expenses = relationship("Expense", back_populates="budget", cascade="all, delete-orphan")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    budget_id = Column(Integer, ForeignKey("monthly_budgets.id"), nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    budget = relationship("MonthlyBudget", back_populates="expenses")
