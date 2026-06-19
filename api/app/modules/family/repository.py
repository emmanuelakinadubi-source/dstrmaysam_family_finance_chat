from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.budget import MonthlyBudget, Expense, BudgetAllocation, Saving
from app.modules.family.schemas import BudgetCreate, ExpenseCreate
from app.modules.family.service import calculate_allocation
import uuid


def create_budget(db: Session, data: BudgetCreate) -> MonthlyBudget:
    total = data.husband_income + data.wife_income
    budget = MonthlyBudget(
        month=data.month,
        year=data.year,
        husband_income=data.husband_income,
        wife_income=data.wife_income,
        total_income=total,
        notes=data.notes,
    )
    db.add(budget)
    db.flush()

    calc = calculate_allocation(data.husband_income, data.wife_income)
    for alloc in calc["allocations"]:
        db.add(BudgetAllocation(
            budget_id=budget.id,
            category=alloc["category"],
            percentage=alloc["percentage"],
            total_amount=alloc["total_amount"],
            husband_amount=alloc["husband_amount"],
            wife_amount=alloc["wife_amount"],
        ))

    for exp in (data.expenses or []):
        db.add(Expense(
            budget_id=budget.id,
            category=exp.category,
            amount=exp.amount,
            description=exp.description,
            vendor=exp.vendor,
        ))

    db.commit()
    db.refresh(budget)
    return budget


def get_budgets(db: Session, skip: int = 0, limit: int = 50) -> List[MonthlyBudget]:
    return (
        db.query(MonthlyBudget)
        .filter(MonthlyBudget.deleted_at.is_(None))
        .order_by(MonthlyBudget.year.desc(), MonthlyBudget.month.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_budget(db: Session, budget_id: uuid.UUID) -> Optional[MonthlyBudget]:
    return (
        db.query(MonthlyBudget)
        .filter(MonthlyBudget.id == budget_id, MonthlyBudget.deleted_at.is_(None))
        .first()
    )


def add_expense(db: Session, budget_id: uuid.UUID, data: ExpenseCreate) -> Expense:
    expense = Expense(budget_id=budget_id, **data.model_dump())
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


def soft_delete_budget(db: Session, budget_id: uuid.UUID) -> bool:
    from datetime import datetime, timezone
    budget = get_budget(db, budget_id)
    if not budget:
        return False
    budget.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return True
