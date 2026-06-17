from pydantic import BaseModel


class IncomeInput(BaseModel):
    husband_income: float
    wife_income: float


class ExpenseInput(BaseModel):
    category: str
    amount: float
