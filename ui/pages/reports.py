import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Reports & Analytics", layout="wide")
st.title("📊 Reports & Analytics")

tab1, tab2, tab3 = st.tabs(["🏠 Family Analytics", "🛒 Vendor Analytics", "📈 Trends"])

# ── Tab 1: Family Analytics ────────────────────────────────────────────────────
with tab1:
    year = st.number_input("Year", min_value=2020, max_value=2100, value=2026, key="family_year")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Load Family Summary"):
            try:
                summary = api.get_family_summary(int(year))
                months = summary.get("months", [])
                if months:
                    df = pd.DataFrame(months)
                    st.dataframe(df[["month","total_income","total_expenses","net"]], use_container_width=True)
                    fig = px.bar(df, x="month", y=["total_income","total_expenses","net"],
                                 barmode="group", title=f"Income vs Expenses — {year}")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No data for this year.")
            except Exception as e:
                st.error(f"Error: {e}")

    with col2:
        if st.button("Category Breakdown"):
            try:
                breakdown = api.get_category_breakdown(int(year))
                if breakdown:
                    df_b = pd.DataFrame(breakdown)
                    fig_b = px.pie(df_b, names="category", values="total",
                                   title=f"Spending by Category — {year}")
                    st.plotly_chart(fig_b, use_container_width=True)
                else:
                    st.info("No expense data for this year.")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 2: Vendor Analytics ────────────────────────────────────────────────────
with tab2:
    v_cat = st.text_input("Filter by category (optional)", key="v_cat")
    if st.button("Load Vendor Analysis"):
        try:
            analysis = api.get_vendor_analysis(category=v_cat or None)
            if analysis:
                df_v = pd.DataFrame(analysis)
                st.dataframe(df_v, use_container_width=True)
                fig_v = px.bar(df_v, x="vendor_name", y="avg_price", color="category",
                               title="Average Price by Vendor")
                st.plotly_chart(fig_v, use_container_width=True)
            else:
                st.info("No vendor data available.")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 3: Historical Trends ──────────────────────────────────────────────────
with tab3:
    if st.button("Load Income & Expense Trends"):
        try:
            trends = api.get_family_trends()
            if trends:
                df_t = pd.DataFrame(trends)
                fig_t = px.line(df_t, x="period", y=["total_income","total_expenses"],
                                title="Income & Expense Trend Over Time", markers=True)
                st.plotly_chart(fig_t, use_container_width=True)
            else:
                st.info("No trend data yet.")
        except Exception as e:
            st.error(f"Error: {e}")

    vtype = st.selectbox("Vendor Type for Price Trends", ["grocery", "catering", "hotel"])
    if st.button("Load Vendor Price Trends"):
        try:
            vt = api.get_vendor_price_trends(vtype)
            if vt:
                df_vt = pd.DataFrame(vt)
                fig_vt = px.line(df_vt, x="crawled_at", y="price", color="vendor_name",
                                 line_group="product_name", title="Vendor Price Trends Over Time",
                                 hover_data=["product_name"])
                st.plotly_chart(fig_vt, use_container_width=True)
            else:
                st.info("No price trend data.")
        except Exception as e:
            st.error(f"Error: {e}")
