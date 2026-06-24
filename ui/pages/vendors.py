import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Vendors", page_icon="🏪", layout="wide")
st.title("🏪 Vendor Intelligence")

tab_recs, tab_db, tab_prices, tab_compare, tab_ai, tab_refresh = st.tabs([
    "🎯 Event Match",
    "📋 Directory",
    "💰 Price Catalog",
    "⚖️ Compare",
    "🤖 AI Reasoning",
    "🔄 Data Refresh",
])

GROCERY_VENDORS = ["Tesco", "Aldi", "Lidl", "Asda", "Morrisons", "Sainsbury's"]

# ── Event Recommendations ─────────────────────────────────────────────────────
with tab_recs:
    st.subheader("Vendor Recommendations for a Saved Event")
    try:
        events = api.list_events()
        if not events:
            st.info("No events yet — upload a plan on the Home page first.")
        else:
            options = {f"{e['event_name']} ({e.get('city', 'N/A')})": e["id"] for e in events}
            default_idx = 0
            if "last_event_id" in st.session_state:
                for i, eid in enumerate(options.values()):
                    if str(eid) == st.session_state["last_event_id"]:
                        default_idx = i
                        break
            selected = st.selectbox("Select event", list(options.keys()), index=default_idx)
            event_id = options[selected]

            if st.button("🔍 Find Matching Vendors", type="primary", use_container_width=True):
                with st.spinner("Matching vendors against event requirements…"):
                    try:
                        recs = api.get_event_recommendations(event_id)
                        budget = recs.get("budget") or 0
                        st.metric("Event Budget", f"£{budget:,.2f}")

                        def _show_vendor_card(label: str, vendor: dict):
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
                            """)

                        c1, c2, c3 = st.columns(3)
                        with c1:
                            _show_vendor_card("🏆 Best Match", recs.get("best_match"))
                        with c2:
                            _show_vendor_card("💰 Cheapest", recs.get("cheapest_match"))
                        with c3:
                            _show_vendor_card("📍 Closest City", recs.get("closest_match"))

                        all_matches = recs.get("all_matches", [])
                        if all_matches:
                            st.subheader("All Matches")
                            df = pd.DataFrame(all_matches)
                            cols = [c for c in ["rank", "vendor_name", "vendor_type", "city",
                                                "price_per_person", "estimated_cost",
                                                "budget_remaining", "fit_score"] if c in df.columns]
                            st.dataframe(
                                df[cols].rename(columns=lambda x: x.replace("_", " ").title()),
                                use_container_width=True,
                            )
                            fig = px.bar(df, x="vendor_name", y="estimated_cost", color="vendor_type",
                                         title="Estimated Cost by Vendor",
                                         labels={"estimated_cost": "Cost (£)", "vendor_name": "Vendor"})
                            if budget:
                                fig.add_hline(y=budget, line_dash="dash", line_color="red",
                                              annotation_text=f"Budget: £{budget:,.0f}")
                            st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Recommendation error: {e}")
    except Exception as e:
        st.error(f"Could not load events: {e}")

# ── Vendor Directory ──────────────────────────────────────────────────────────
with tab_db:
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
            cols = [c for c in ["vendor_name", "vendor_type", "city", "price_per_person",
                                 "currency", "description"] if c in df_v.columns]
            st.dataframe(
                df_v[cols].rename(columns=lambda x: x.replace("_", " ").title()),
                use_container_width=True,
            )
            fig_v = px.scatter(df_v, x="city", y="price_per_person", color="vendor_type",
                               size="price_per_person", hover_data=["vendor_name"],
                               title="Vendor Pricing by City and Type")
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("No vendors found.")
    except Exception as e:
        st.error(f"Could not load vendors: {e}")

# ── Price Catalog ─────────────────────────────────────────────────────────────
with tab_prices:
    c1, c2 = st.columns(2)
    vtype = c1.selectbox(
        "Vendor Type",
        ["", "grocery", "catering", "hotel", "conference", "raw_food"],
        format_func=lambda x: "All" if x == "" else x,
        key="price_vtype",
    )
    cat = c2.text_input("Category filter (optional)", key="price_cat")

    try:
        prices = api.list_vendor_prices(vendor_type=vtype or None, category=cat or None)
        if prices:
            df = pd.DataFrame(prices)
            st.dataframe(
                df[["vendor_name", "product_name", "price", "currency", "category", "vendor_type"]],
                use_container_width=True,
            )
            fig = px.bar(df, x="product_name", y="price", color="vendor_name",
                         barmode="group", title="Price by Product & Vendor")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No price data yet. Run a Data Refresh to populate.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Compare Vendors ───────────────────────────────────────────────────────────
with tab_compare:
    selected_vendors = st.multiselect(
        "Select vendors to compare", GROCERY_VENDORS, default=["Tesco", "Aldi"]
    )
    compare_cat = st.text_input("Product category (optional)", key="compare_cat")

    if st.button("Compare", use_container_width=True, key="compare_btn") and selected_vendors:
        try:
            results = api.compare_vendors(selected_vendors, category=compare_cat or None)
            if results:
                df_c = pd.DataFrame(results)
                st.dataframe(
                    df_c[["vendor_name", "product_name", "price", "category"]],
                    use_container_width=True,
                )
                fig_c = px.bar(df_c, x="product_name", y="price", color="vendor_name",
                               barmode="group", title="Head-to-Head Price Comparison")
                st.plotly_chart(fig_c, use_container_width=True)

                cheapest = df_c.groupby("vendor_name")["price"].mean().reset_index()
                cheapest.columns = ["Vendor", "Avg Price (£)"]
                cheapest = cheapest.sort_values("Avg Price (£)")
                st.subheader("Cheapest Overall")
                st.dataframe(cheapest.reset_index(drop=True), use_container_width=True)
            else:
                st.info("No data found for selected vendors.")
        except Exception as e:
            st.error(f"Error: {e}")

# ── AI Vendor Reasoning ───────────────────────────────────────────────────────
with tab_ai:
    st.subheader("AI-Powered Vendor Reasoning")
    st.markdown("The Vendor Agent reasons about vendor selection and explains its recommendations.")

    c1, c2 = st.columns(2)
    ai_city = c1.text_input("Event City", value="London", key="ai_city")
    ai_attendees = c2.number_input("Attendees", min_value=1, value=100, step=10, key="ai_att")
    c3, c4 = st.columns(2)
    ai_budget = c3.number_input("Budget (£)", min_value=0.0, value=15000.0, step=500.0, key="ai_bud")
    ai_days = c4.number_input("Duration (days)", min_value=1, value=2, step=1, key="ai_days")
    ai_food = st.checkbox("Food/Catering Required", value=True, key="ai_food")
    ai_hosting = st.checkbox("Hotel/Accommodation Required", value=True, key="ai_host")

    if st.button("🤖 Get AI Recommendation", type="primary", use_container_width=True, key="ai_btn"):
        with st.spinner("Vendor agent is reasoning about your requirements…"):
            try:
                result = api.get_vendor_ai_recommendation(
                    city=ai_city, attendee_count=int(ai_attendees), budget=ai_budget,
                    number_of_days=int(ai_days), food_required=ai_food, hosting_required=ai_hosting,
                )
                st.markdown("### Agent Recommendation")
                st.markdown(result.get("recommendation", "No recommendation generated."))
            except Exception as e:
                st.error(f"AI recommendation error: {e}")

# ── Data Refresh ──────────────────────────────────────────────────────────────
with tab_refresh:
    st.subheader("Vendor & Hotel Data Refresh")
    st.markdown(
        "Data is scraped from **OpenStreetMap** for 7 UK cities "
        "(London, Manchester, Birmingham, Edinburgh, Bristol, Leeds, Glasgow). "
        "Automatic crawl runs every **Sunday at 02:00 UTC**."
    )

    try:
        schedule = api.get_crawl_schedule()
        c1, c2 = st.columns(2)
        c1.metric("Next venue indexing", schedule.get("daily_venue_indexing", "unknown")[:19])
        c2.metric("Next vendor crawl", schedule.get("weekly_vendor_crawl", "unknown")[:19])
    except Exception:
        pass

    st.divider()
    col_bg, col_fg = st.columns(2)

    with col_bg:
        st.caption("Starts crawl in background — returns immediately")
        if st.button("▶ Run in Background", use_container_width=True, key="crawl_bg"):
            try:
                result = api.trigger_vendor_crawl()
                st.success(result.get("message", "Crawl started"))
            except Exception as e:
                st.error(f"Error: {e}")

    with col_fg:
        st.caption("Blocks until complete — shows full result")
        if st.button("⏳ Run & Wait", type="primary", use_container_width=True, key="crawl_fg"):
            with st.spinner("Scraping hotels and caterers for 7 UK cities — ~2 minutes…"):
                try:
                    result = api._post("/vendors/crawl?foreground=true", {})
                    if result.get("status") == "ok":
                        st.success("Crawl complete")
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("New vendors", result.get("vendors_new", 0))
                        m2.metric("Updated vendors", result.get("vendors_updated", 0))
                        m3.metric("New prices", result.get("prices_new", 0))
                        m4.metric("Updated prices", result.get("prices_updated", 0))
                    else:
                        st.error(f"Crawl error: {result.get('error')}")
                except Exception as e:
                    st.error(f"Error: {e}")
