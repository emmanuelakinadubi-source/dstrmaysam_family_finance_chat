import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Company Events", page_icon="📅", layout="wide")
st.title("🏢 Company Events & Budget Planning")

tab1, tab2, tab3 = st.tabs(["📅 New Event", "💼 Company Budgets", "🎯 Vendor Matching"])

# ── Tab 1: New Event ──────────────────────────────────────────────────────────
with tab1:
    st.subheader("Create Event Plan")
    with st.form("event_form"):
        c1, c2 = st.columns(2)
        event_name = c1.text_input("Event Name *")
        event_date = c2.date_input("Event Date")
        c3, c4 = st.columns(2)
        attendee_count = c3.number_input("Attendees", min_value=1, step=1, value=50)
        budget = c4.number_input("Total Budget (£)", min_value=0.0, step=100.0)
        c5, c6 = st.columns(2)
        venue = c5.text_input("Venue")
        hotel = c6.text_input("Hotel / Accommodation")
        food_requirements = st.text_area("Food Requirements")
        c7, c8 = st.columns(2)
        welfare_budget = c7.number_input("Welfare Budget (£)", min_value=0.0, step=50.0)
        location = c8.text_input("Location")
        special_requirements = st.text_area("Special Requirements")
        submitted = st.form_submit_button("Create Event Plan", type="primary")

    if submitted and event_name:
        try:
            event = api.create_event(
                event_name=event_name,
                event_date=str(event_date),
                attendee_count=int(attendee_count),
                budget=budget,
                venue=venue or None,
                hotel=hotel or None,
                food_requirements=food_requirements or None,
                welfare_budget=welfare_budget or None,
                location=location or None,
                special_requirements=special_requirements or None,
            )
            st.success(f"Event created — ID: {event['id']}")
        except Exception as e:
            st.error(f"Error: {e}")

    st.subheader("Event Plans")
    try:
        events = api.list_events()
        if events:
            df = pd.DataFrame(events)[["event_name","event_date","attendee_count","budget","status"]]
            df.columns = ["Event","Date","Attendees","Budget (£)","Status"]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No events yet.")
    except Exception as e:
        st.error(f"Could not load events: {e}")

# ── Tab 2: Company Budgets ────────────────────────────────────────────────────
with tab2:
    st.subheader("Create Company Budget")
    with st.form("company_budget_form"):
        c1, c2 = st.columns(2)
        title = c1.text_input("Budget Title *")
        department = c2.text_input("Department")
        total_budget = st.number_input("Total Budget (£)", min_value=0.0, step=100.0)
        c3, c4 = st.columns(2)
        period_start = c3.text_input("Period Start (e.g. Jan 2026)")
        period_end = c4.text_input("Period End (e.g. Dec 2026)")
        sub2 = st.form_submit_button("Create Budget")

    if sub2 and title:
        try:
            cb = api.create_company_budget(
                title=title, total_budget=total_budget,
                department=department or None,
                period_start=period_start or None,
                period_end=period_end or None,
            )
            st.success(f"Company budget created — ID: {cb['id']}")
        except Exception as e:
            st.error(f"Error: {e}")

    st.subheader("Company Budgets")
    try:
        cbs = api.list_company_budgets()
        if cbs:
            df_cb = pd.DataFrame(cbs)[["title","department","total_budget","period_start","period_end","status"]]
            df_cb.columns = ["Title","Department","Total Budget (£)","Start","End","Status"]
            st.dataframe(df_cb, use_container_width=True)
    except Exception as e:
        st.error(f"Could not load company budgets: {e}")

# ── Tab 3: Vendor Matching ────────────────────────────────────────────────────
with tab3:
    st.subheader("Find Vendors That Fit Your Event")
    c1, c2 = st.columns(2)
    ev_budget = c1.number_input("Event Budget (£)", min_value=0.0, step=100.0, value=5000.0)
    ev_attendees = c2.number_input("Attendees", min_value=1, step=1, value=50)
    vendor_type = st.selectbox("Vendor Type", ["catering", "grocery", "hotel", "conference", "accommodation"])

    if st.button("Find Matching Vendors"):
        try:
            matches = api.match_vendors(ev_budget, int(ev_attendees), vendor_type)
            if matches:
                df_m = pd.DataFrame(matches)
                st.dataframe(df_m, use_container_width=True)
                fig = px.bar(df_m, x="vendor_name", y="estimated_total",
                             color="fit_score", title="Vendor Cost vs Fit Score")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No matching vendors found. Try running a vendor crawl first.")
        except Exception as e:
            st.error(f"Error: {e}")
