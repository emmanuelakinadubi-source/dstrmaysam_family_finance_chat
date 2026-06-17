from fastapi import APIRouter

router = APIRouter(tags=["budget"])


@router.get("/budget/sample")
def sample_budget():
    return {
        "month": "January",
        "year": 2026,
        "total_income": 0,
        "total_expenses": 0
    }
