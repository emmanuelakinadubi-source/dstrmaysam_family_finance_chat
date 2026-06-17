def calculate_total_income(husband_income: float, wife_income: float) -> float:
    return husband_income + wife_income


def contribution_share(income: float, total_income: float) -> float:
    if total_income == 0:
        return 0.0
    return round((income / total_income) * 100, 2)
