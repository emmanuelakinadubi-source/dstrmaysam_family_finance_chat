import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.modules.family import repository as repo
from app.modules.family.service import calculate_allocation
from app.modules.family.schemas import (
    BudgetCreate, BudgetOut, ExpenseCreate, ExpenseOut,
    IncomeInput, BudgetCalculation,
)

router = APIRouter(prefix="/family", tags=["Family Finance"])


@router.post("/calculate", response_model=BudgetCalculation)
def calculate(data: IncomeInput):
    return calculate_allocation(data.husband_income, data.wife_income)


@router.post("/budgets", response_model=BudgetOut, status_code=status.HTTP_201_CREATED)
def create_budget(data: BudgetCreate, db: Session = Depends(get_db)):
    return repo.create_budget(db, data)


@router.get("/budgets", response_model=List[BudgetOut])
def list_budgets(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return repo.get_budgets(db, skip, limit)


@router.get("/budgets/{budget_id}", response_model=BudgetOut)
def get_budget(budget_id: uuid.UUID, db: Session = Depends(get_db)):
    budget = repo.get_budget(db, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.post("/budgets/{budget_id}/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def add_expense(budget_id: uuid.UUID, data: ExpenseCreate, db: Session = Depends(get_db)):
    if not repo.get_budget(db, budget_id):
        raise HTTPException(status_code=404, detail="Budget not found")
    return repo.add_expense(db, budget_id, data)


@router.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(budget_id: uuid.UUID, db: Session = Depends(get_db)):
    if not repo.soft_delete_budget(db, budget_id):
        raise HTTPException(status_code=404, detail="Budget not found")
