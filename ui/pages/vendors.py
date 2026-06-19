import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Vendor Recommendations", layout="wide")
st.title("🏪 Vendor Recommendations")

tab1, tab2, tab3 = st.tabs(["🎯 Event Recommendations", "📊 All Vendors", "🤖 AI Vendor Reasoning"])

# ── Tab 1: Event-Based Recommendations ────────────────────────────────────────
with tab1:
    st.subheader("Get Vendor Recommendations for an Event")

    try:
        events = api.list_events()
        if not events:
            st.info("No events yet — upload a plan first.")
        else:
            options = {f"{e['event_name']} ({e.get('city', 'N/A')})": e["id"] for e in events}

            # Pre-select last uploaded event if available
            default_idx = 0
            if "last_event_id" in st.session_state:
                for i, eid in enumerate(options.values()):
                    if str(eid) == st.session_state["last_event_id"]:
                        default_idx = i
                        break

            selected = st.selectbox("Select event", list(options.keys()), index=default_idx)
            event_id = options[selected]

            if st.button("🔍 Find Matching Vendors", type="primary", use_container_width=True):
                with st.spinner("Matching vendors against event requirements..."):
                    try:
                        recs = api.get_event_recommendations(event_id)

                        budget = recs.get("budget") or 0
                        st.metric("Event Budget", f"£{budget:,.2f}")

                        def show_vendor_card(label: str, vendor: dict):
                            if not vendor:
                                st.warning(f"{label}: No match found")
                                return
                            remaining = vendor.get("budget_remaining", 0)
                            color = "🟢" if remaining >= 0 else "🔴"
                            st.markdown(f"""
                            **{label}**
                            - **{vendor['vendor_name']}** ({vendor['vendor_type']}) — {vendor['city']}
                            - Price per person: £{vendor['price_per_person']:,.2f}
                            - Estimated cost: **£{vendor['estimated_cost']:,.2f}**
                            - Budget remaining: {color} **£{abs(remaining):,.2f}** {'surplus' if remaining >= 0 else 'shortfall'}
                            - Fit score: {vendor.get('fit_score', 0):.0%}
                            - City match: {"✅" if vendor.get('city_match') else "❌"}
                            """)

                        c1, c2, c3 = st.columns(3)
                        with c1:
                            show_vendor_card("🏆 Best Match", recs.get("best_match"))
                        with c2:
                            show_vendor_card("💰 Cheapest Match", recs.get("cheapest_match"))
                        with c3:
                            show_vendor_card("📍 Closest Match", recs.get("closest_match"))

                        all_matches = recs.get("all_matches", [])
                        if all_matches:
                            st.subheader("All Matches")
                            df = pd.DataFrame(all_matches)
                            cols = [c for c in ["rank", "vendor_name", "vendor_type", "city", "price_per_person",
                                                "estimated_cost", "budget_remaining", "fit_score", "city_match"] if c in df.columns]
                            st.dataframe(df[cols].rename(columns=lambda x: x.replace("_", " ").title()),
                                         use_container_width=True)

                            fig = px.bar(df, x="vendor_name", y="estimated_cost",
                                         color="vendor_type", title="Estimated Cost by Vendor",
                                         labels={"estimated_cost": "Estimated Cost (£)", "vendor_name": "Vendor"})
                            if budget:
                                fig.add_hline(y=budget, line_dash="dash", line_color="red",
                                              annotation_text=f"Budget: £{budget:,.0f}")
                            st.plotly_chart(fig, use_container_width=True)

                    except Exception as e:
                        st.error(f"Recommendation error: {e}")
    except Exception as e:
        st.error(f"Could not load events: {e}")

# ── Tab 2: All Vendors ─────────────────────────────────────────────────────────
with tab2:
    st.subheader("Vendor Database")
    c1, c2 = st.columns(2)
    filter_city = c1.text_input("Filter by city")
    filter_type = c2.selectbox("Filter by type", ["All", "Catering", "Hotel", "Conference"])

    try:
        vendors = api.list_vendors(
            city=filter_city or None,
            vendor_type=None if filter_type == "All" else filter_type,
        )
        if vendors:
            df_v = pd.DataFrame(vendors)
            cols = [c for c in ["vendor_name", "vendor_type", "city", "price_per_person", "currency", "description"] if c in df_v.columns]
            st.dataframe(df_v[cols].rename(columns=lambda x: x.replace("_", " ").title()),
                         use_container_width=True)

            fig_v = px.scatter(df_v, x="city", y="price_per_person", color="vendor_type",
                               size="price_per_person", hover_data=["vendor_name"],
                               title="Vendor Pricing by City and Type")
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("No vendors found.")
    except Exception as e:
        st.error(f"Could not load vendors: {e}")

# ── Tab 3: AI Vendor Reasoning ────────────────────────────────────────────────
with tab3:
    st.subheader("AI-Powered Vendor Reasoning")
    st.markdown("The Vendor Agent will reason about vendor selection and explain its recommendations.")

    c1, c2 = st.columns(2)
    city = c1.text_input("Event City", value="London")
    attendees = c2.number_input("Attendees", min_value=1, value=100, step=10)
    c3, c4 = st.columns(2)
    budget = c3.number_input("Budget (£)", min_value=0.0, value=15000.0, step=500.0)
    days = c4.number_input("Duration (days)", min_value=1, value=2, step=1)
    food = st.checkbox("Food/Catering Required", value=True)
    hosting = st.checkbox("Hotel/Accommodation Required", value=True)

    if st.button("🤖 Get AI Recommendation", type="primary", use_container_width=True):
        with st.spinner("Vendor agent is reasoning about your requirements..."):
            try:
                result = api.get_vendor_ai_recommendation(
                    city=city, attendee_count=int(attendees), budget=budget,
                    number_of_days=int(days), food_required=food, hosting_required=hosting,
                )
                st.markdown("### Agent Recommendation")
                st.markdown(result.get("recommendation", "No recommendation generated."))
            except Exception as e:
                st.error(f"AI recommendation error: {e}")
