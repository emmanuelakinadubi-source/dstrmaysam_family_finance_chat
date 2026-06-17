import streamlit as st
import requests

st.set_page_config(page_title="Family Finance Chat App", layout="wide")

st.title("Family Finance Chat App")
st.write("Monthly budgeting and contribution planner")

with st.sidebar:
    st.header("Month Setup")
    month = st.selectbox("Month", [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ])
    year = st.number_input("Year", min_value=2024, max_value=2100, value=2026)

st.subheader("Income")
col1, col2 = st.columns(2)
with col1:
    husband_income = st.number_input("Husband income (£)", min_value=0.0, step=100.0)
with col2:
    wife_income = st.number_input("Wife income (£)", min_value=0.0, step=100.0)

if st.button("Calculate"):
    total_income = husband_income + wife_income
    st.success(f"Total household income: £{total_income:,.2f}")

    try:
        health = requests.get("http://api:8000/api/health", timeout=5)
        st.info(f"API status: {health.json()}")
    except Exception:
        st.warning("API is not reachable yet.")
