import streamlit as st

st.set_page_config(page_title="Family Budget", layout="wide")

st.warning(
    "🔒 **Family Budget module is disabled in the current MVP phase.** "
    "This feature will be enabled in Phase 2. "
    "Please use the **Dashboard**, **Upload**, **Vendors**, or **Chat** pages."
)

st.title("🏠 Family Budget Planner — Phase 2")
st.markdown(
    """
    This module will support:
    - Monthly household income entry (Husband + Wife)
    - Budget allocation across Expenses, Savings, Emergency Fund, Tithe
    - Expense tracking by category (Groceries, Rent, Car Loan, etc.)
    - Grocery vendor price comparisons (Tesco, Aldi, Lidl, Asda, Morrisons, Sainsbury's)
    - Historical budget trends and reports

    **Coming in Phase 2.**
    """
)

st.button("Go to Dashboard", on_click=lambda: None, disabled=True)
