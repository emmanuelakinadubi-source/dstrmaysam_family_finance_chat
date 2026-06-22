from typing import List, Optional
from app.models.budget import ALLOCATION_DEFAULTS, ADJUSTMENT_PRIORITY

GROCERY_VENDORS = ["Tesco", "Aldi", "Lidl", "Asda", "Morrisons", "Sainsbury's"]


def calculate_allocation(husband_income: float, wife_income: float) -> dict:
    total = husband_income + wife_income
    if total == 0:
        return {"error": "Total income cannot be zero"}

    husband_pct = round((husband_income / total) * 100, 2)
    wife_pct = round((wife_income / total) * 100, 2)

    allocations = []
    for category, pct in ALLOCATION_DEFAULTS.items():
        amount = total * pct
        allocations.append({
            "category": category,
            "percentage": pct * 100,
            "total_amount": round(amount, 2),
            "husband_amount": round(amount * (husband_pct / 100), 2),
            "wife_amount": round(amount * (wife_pct / 100), 2),
        })

    return {
        "total_income": round(total, 2),
        "husband_income": round(husband_income, 2),
        "wife_income": round(wife_income, 2),
        "husband_percentage": husband_pct,
        "wife_percentage": wife_pct,
        "allocations": allocations,
    }


def adjust_for_deficit(
    total_income: float,
    total_expenses: float,
    allocations: List[dict],
) -> dict:
    """Trim allocations in priority order when income cannot meet targets."""
    deficit = total_expenses - total_income
    if deficit <= 0:
        return {"adjusted": False, "allocations": allocations, "deficit": 0}

    remaining_deficit = deficit
    recommendations: List[str] = []
    adjusted = [a.copy() for a in allocations]
    alloc_map = {a["category"]: a for a in adjusted}

    for category in ADJUSTMENT_PRIORITY:
        if remaining_deficit <= 0:
            break
        alloc = alloc_map.get(category)
        if not alloc:
            continue
        cut = min(alloc["total_amount"], remaining_deficit)
        alloc["total_amount"] = round(alloc["total_amount"] - cut, 2)
        alloc["husband_amount"] = round(alloc["husband_amount"] * (alloc["total_amount"] / (alloc["total_amount"] + cut) if alloc["total_amount"] + cut > 0 else 0), 2)
        alloc["wife_amount"] = round(alloc["wife_amount"] * (alloc["total_amount"] / (alloc["total_amount"] + cut) if alloc["total_amount"] + cut > 0 else 0), 2)
        remaining_deficit -= cut
        recommendations.append(f"Reduced {category.replace('_', ' ')} by £{cut:.2f}")

    return {
        "adjusted": True,
        "deficit": round(deficit, 2),
        "allocations": adjusted,
        "recommendations": recommendations,
    }
