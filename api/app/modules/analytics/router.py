from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/family/trends")
def family_income_expense_trend(db: Session = Depends(get_db)):
    from app.models.budget import MonthlyBudget, Expense

    budgets = (
        db.query(MonthlyBudget)
        .filter(MonthlyBudget.deleted_at.is_(None))
        .order_by(MonthlyBudget.year, MonthlyBudget.month)
        .all()
    )
    return [
        {
            "period": f"{b.month} {b.year}",
            "total_income": b.total_income,
            "total_expenses": sum(e.amount for e in b.expenses),
            "husband_income": b.husband_income,
            "wife_income": b.wife_income,
        }
        for b in budgets
    ]


@router.get("/family/category-breakdown")
def category_breakdown(year: int, db: Session = Depends(get_db)):
    from app.models.budget import MonthlyBudget, Expense

    rows = (
        db.query(Expense.category, func.sum(Expense.amount).label("total"))
        .join(MonthlyBudget)
        .filter(MonthlyBudget.year == year, MonthlyBudget.deleted_at.is_(None))
        .group_by(Expense.category)
        .all()
    )
    return [{"category": r.category, "total": round(r.total, 2)} for r in rows]


@router.get("/vendors/price-trends")
def vendor_price_trends(vendor_type: str = "grocery", db: Session = Depends(get_db)):
    from app.models.vendor import VendorPrice

    rows = (
        db.query(VendorPrice)
        .filter(VendorPrice.vendor_type == vendor_type)
        .order_by(VendorPrice.crawled_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "vendor_name": r.vendor_name,
            "product_name": r.product_name,
            "price": r.price,
            "currency": r.currency,
            "category": r.category,
            "crawled_at": r.crawled_at.isoformat() if r.crawled_at else None,
        }
        for r in rows
    ]
