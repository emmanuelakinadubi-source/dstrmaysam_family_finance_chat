import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.budget import CompanyBudget, BudgetItem
from app.models.event import EventPlan
from app.modules.company.schemas import (
    CompanyBudgetCreate, CompanyBudgetOut,
    EventPlanCreate, EventPlanOut,
)

router = APIRouter(prefix="/company", tags=["Company"])


@router.post("/budgets", response_model=CompanyBudgetOut, status_code=status.HTTP_201_CREATED)
def create_company_budget(data: CompanyBudgetCreate, db: Session = Depends(get_db)):
    budget = CompanyBudget(
        title=data.title,
        department=data.department,
        total_budget=data.total_budget,
        period_start=data.period_start,
        period_end=data.period_end,
        notes=data.notes,
    )
    db.add(budget)
    db.flush()
    for item in (data.items or []):
        db.add(BudgetItem(budget_id=budget.id, **item.model_dump()))
    db.commit()
    db.refresh(budget)
    return budget


@router.get("/budgets", response_model=List[CompanyBudgetOut])
def list_company_budgets(db: Session = Depends(get_db)):
    return db.query(CompanyBudget).filter(CompanyBudget.deleted_at.is_(None)).all()


@router.get("/budgets/{budget_id}", response_model=CompanyBudgetOut)
def get_company_budget(budget_id: uuid.UUID, db: Session = Depends(get_db)):
    budget = db.query(CompanyBudget).filter(
        CompanyBudget.id == budget_id, CompanyBudget.deleted_at.is_(None)
    ).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    return budget


@router.post("/events", response_model=EventPlanOut, status_code=status.HTTP_201_CREATED)
def create_event(data: EventPlanCreate, db: Session = Depends(get_db)):
    event = EventPlan(**data.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.get("/events", response_model=List[EventPlanOut])
def list_events(db: Session = Depends(get_db)):
    return db.query(EventPlan).filter(EventPlan.deleted_at.is_(None)).all()


@router.get("/events/{event_id}", response_model=EventPlanOut)
def get_event(event_id: uuid.UUID, db: Session = Depends(get_db)):
    event = db.query(EventPlan).filter(
        EventPlan.id == event_id, EventPlan.deleted_at.is_(None)
    ).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
