import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Company Event Planning — Dashboard")

# ── Stats ──────────────────────────────────────────────────────────────────────
try:
    stats = api.get_dashboard_stats()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Events", stats.get("total_events", 0))
    c2.metric("Total Budget", f"£{stats.get('total_budget', 0):,.2f}")
    c3.metric("Vendors Available", stats.get("total_vendors", 0))
except Exception as e:
    st.warning(f"Could not load stats: {e}")
    stats = {}

st.divider()

# ── Recent Events ──────────────────────────────────────────────────────────────
st.subheader("Recent Events")
try:
    events = api.list_events()
    if events:
        df = pd.DataFrame(events)
        cols = [c for c in ["event_name", "city", "event_date", "attendee_count", "budget", "status"] if c in df.columns]
        display = df[cols].copy()
        display.columns = [c.replace("_", " ").title() for c in cols]
        st.dataframe(display, use_container_width=True)

        # Budget chart
        budget_data = df[df["budget"].notna()]
        if not budget_data.empty:
            fig = px.bar(budget_data, x="event_name", y="budget",
                         color="city", title="Event Budgets by City",
                         labels={"budget": "Budget (£)", "event_name": "Event"})
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No events yet — upload an event plan to get started.")
except Exception as e:
    st.error(f"Could not load events: {e}")

# ── Vendor Overview ────────────────────────────────────────────────────────────
st.subheader("Vendor Overview")
try:
    prices = api.list_vendor_prices()
    if prices:
        df_v = pd.DataFrame(prices)
        if "vendor_type" in df_v.columns and "city" in df_v.columns:
            pivot = df_v.groupby(["city", "vendor_type"]).size().reset_index(name="count")
            fig_v = px.bar(pivot, x="city", y="count", color="vendor_type",
                           title="Vendors by City and Type", barmode="group")
            st.plotly_chart(fig_v, use_container_width=True)
except Exception as e:
    st.caption(f"Vendor chart unavailable: {e}")
