from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.report import Report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/")
def list_reports(db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.deleted_at.is_(None)).order_by(Report.created_at.desc()).all()


@router.get("/family/summary")
def family_summary(year: int, db: Session = Depends(get_db)):
    from app.models.budget import MonthlyBudget, Expense
    budgets = (
        db.query(MonthlyBudget)
        .filter(MonthlyBudget.year == year, MonthlyBudget.deleted_at.is_(None))
        .all()
    )
    summary = []
    for b in budgets:
        total_expenses = sum(e.amount for e in b.expenses)
        summary.append({
            "month": b.month,
            "year": b.year,
            "total_income": b.total_income,
            "total_expenses": total_expenses,
            "net": round(b.total_income - total_expenses, 2),
        })
    return {"year": year, "months": summary}


@router.get("/vendors/analysis")
def vendor_analysis(category: str = None, db: Session = Depends(get_db)):
    from app.models.vendor import VendorPrice
    from sqlalchemy import func

    q = db.query(
        VendorPrice.vendor_name,
        VendorPrice.category,
        func.avg(VendorPrice.price).label("avg_price"),
        func.min(VendorPrice.price).label("min_price"),
        func.max(VendorPrice.price).label("max_price"),
        func.count(VendorPrice.id).label("product_count"),
    ).group_by(VendorPrice.vendor_name, VendorPrice.category)

    if category:
        q = q.filter(VendorPrice.category == category)

    rows = q.all()
    return [
        {
            "vendor_name": r.vendor_name,
            "category": r.category,
            "avg_price": round(r.avg_price, 2),
            "min_price": round(r.min_price, 2),
            "max_price": round(r.max_price, 2),
            "product_count": r.product_count,
        }
        for r in rows
    ]
