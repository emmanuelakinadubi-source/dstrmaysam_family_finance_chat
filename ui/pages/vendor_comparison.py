import streamlit as st
import pandas as pd
import plotly.express as px
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Vendor Comparison", layout="wide")
st.title("🛒 Vendor Price Intelligence")

tab1, tab2, tab3 = st.tabs(["💰 All Prices", "⚖️ Compare Vendors", "🔄 Data Refresh"])

GROCERY_VENDORS = ["Tesco", "Aldi", "Lidl", "Asda", "Morrisons", "Sainsbury's"]

# ── Tab 1: All Prices ──────────────────────────────────────────────────────────
with tab1:
    c1, c2 = st.columns(2)
    vtype = c1.selectbox("Vendor Type", ["", "grocery", "catering", "hotel", "conference", "raw_food"],
                         format_func=lambda x: "All" if x == "" else x)
    cat = c2.text_input("Category filter (optional)")

    try:
        prices = api.list_vendor_prices(vendor_type=vtype or None, category=cat or None)
        if prices:
            df = pd.DataFrame(prices)
            st.dataframe(
                df[["vendor_name","product_name","price","currency","category","vendor_type"]],
                use_container_width=True,
            )
            fig = px.bar(df, x="product_name", y="price", color="vendor_name",
                         barmode="group", title="Price by Product & Vendor")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No price data yet. Run a data refresh below.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Tab 2: Compare Specific Vendors ────────────────────────────────────────────
with tab2:
    selected_vendors = st.multiselect("Select vendors to compare", GROCERY_VENDORS, default=["Tesco", "Aldi"])
    compare_cat = st.text_input("Product category (optional)")

    if st.button("Compare", use_container_width=True) and selected_vendors:
        try:
            results = api.compare_vendors(selected_vendors, category=compare_cat or None)
            if results:
                df_c = pd.DataFrame(results)
                st.dataframe(df_c[["vendor_name","product_name","price","category"]], use_container_width=True)

                fig_c = px.bar(df_c, x="product_name", y="price", color="vendor_name",
                               barmode="group", title="Head-to-Head Price Comparison")
                st.plotly_chart(fig_c, use_container_width=True)

                cheapest = df_c.groupby("vendor_name")["price"].mean().reset_index()
                cheapest.columns = ["Vendor", "Avg Price (£)"]
                cheapest = cheapest.sort_values("Avg Price (£)")
                st.subheader("Overall Cheapest Vendor")
                st.dataframe(cheapest.reset_index(drop=True), use_container_width=True)
            else:
                st.info("No data found for selected vendors.")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 3: Data Refresh ────────────────────────────────────────────────────────
with tab3:
    st.subheader("Vendor & Hotel Data Refresh")
    st.markdown(
        "Vendor and hotel data is scraped from **OpenStreetMap** for 7 UK cities "
        "(London, Manchester, Birmingham, Edinburgh, Bristol, Leeds, Glasgow). "
        "The scheduled crawl runs automatically every **Sunday at 02:00 UTC**."
    )

    # Show next scheduled runs
    try:
        schedule = api._get("/vendors/crawl/schedule")
        c1, c2 = st.columns(2)
        c1.metric("Next venue indexing", schedule.get("daily_venue_indexing", "unknown")[:19])
        c2.metric("Next vendor crawl", schedule.get("weekly_vendor_crawl", "unknown")[:19])
    except Exception:
        pass

    st.divider()
    col_bg, col_fg = st.columns(2)

    with col_bg:
        st.caption("Starts crawl in background — returns immediately")
        if st.button("▶ Run in Background", use_container_width=True):
            try:
                result = api.trigger_vendor_crawl()
                st.success(result.get("message", "Crawl started"))
            except Exception as e:
                st.error(f"Error: {e}")

    with col_fg:
        st.caption("Blocks until complete — shows full result summary")
        if st.button("⏳ Run & Wait for Result", type="primary", use_container_width=True):
            with st.spinner("Scraping hotels and caterers for 7 UK cities — this takes ~2 minutes…"):
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
