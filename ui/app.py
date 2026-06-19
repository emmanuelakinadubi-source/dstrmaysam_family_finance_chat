import streamlit as st

st.set_page_config(
    page_title="Company Event Budgeting & Vendor AI",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏢 Company Event Budgeting & Vendor Recommendation System")

st.markdown("""
### MVP — End-to-End Company Event Workflow

| Page | Description | Status |
|---|---|---|
| 📊 Dashboard | Overview of events, budgets and vendors | ✅ Active |
| 📤 Upload | Upload event plan → AI extracts details | ✅ Active |
| 🏪 Vendors | Vendor recommendations & AI reasoning | ✅ Active |
| 💬 Chat | Ask questions about uploaded event docs | ✅ Active |
| 🏠 Family Budget | Household budgeting module | 🔒 Phase 2 |
| 📈 Reports | Analytics & historical reports | 🔒 Phase 2 |
""")

st.info(
    "**Getting started:** Use the sidebar to navigate. "
    "Start by uploading an event plan on the **Upload** page."
)

try:
    from ui.services.api_client import get_health
    health = get_health()
    st.sidebar.success(f"API: {health.get('status', 'ok')}")
except Exception:
    st.sidebar.warning("⚠️ API not reachable — start Docker services")

st.sidebar.divider()
st.sidebar.caption("Family Budget and Reports modules are available but disabled in this MVP phase.")
