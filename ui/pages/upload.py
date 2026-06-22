import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Event Upload", layout="wide")
st.title("📤 Event Plan Upload")
st.markdown(
    "Upload a company event plan document. The AI will extract event details automatically."
)

SUPPORTED = ["pdf", "docx", "xlsx", "csv"]

# ── Upload Form ────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Choose a file",
    type=SUPPORTED,
    help="Supported formats: PDF, Word (DOCX), Excel (XLSX), CSV",
)

if uploaded:
    st.info(f"File ready: **{uploaded.name}** ({uploaded.size:,} bytes)")

    if st.button("🚀 Upload & Extract Event Details", type="primary", use_container_width=True):
        with st.spinner("Parsing document and extracting event details via AI agent..."):
            try:
                result = api.upload_event_plan(uploaded)

                st.success("Event plan processed successfully!")

                extracted = result.get("extracted", {})
                event_id = result.get("event_id")

                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Extracted Event Details")
                    fields = [
                        ("Event Name", extracted.get("event_name")),
                        ("City", extracted.get("city")),
                        ("Date", extracted.get("event_date")),
                        ("Time", extracted.get("event_time")),
                        ("Attendees", extracted.get("attendee_count")),
                        ("Duration (days)", extracted.get("number_of_days")),
                        ("Food Required", extracted.get("food_required")),
                        ("Hosting Required", extracted.get("hosting_required")),
                        ("Budget", f"£{extracted.get('budget', 0):,.2f}" if extracted.get("budget") else "N/A"),
                    ]
                    for label, value in fields:
                        if value is not None:
                            icon = "✅" if value is True else ("❌" if value is False else "•")
                            st.markdown(f"**{label}:** {icon} {value}")

                with col2:
                    st.subheader("Next Steps")
                    st.markdown(f"""
                    - **Event ID:** `{event_id}`
                    - Document indexed in ChromaDB ✅
                    - Go to **Vendor Recommendations** to find matching vendors
                    - Go to **Chat** to ask questions about this document
                    """)
                    if event_id:
                        st.session_state["last_event_id"] = event_id
                        st.session_state["last_event_name"] = extracted.get("event_name", "Event")

            except Exception as e:
                st.error(f"Upload failed: {e}")

st.divider()

# ── Existing Events ────────────────────────────────────────────────────────────
st.subheader("All Uploaded Events")
try:
    events = api.list_events()
    if events:
        df = pd.DataFrame(events)
        cols = [c for c in ["event_name", "city", "event_date", "attendee_count", "budget", "food_required", "hosting_required", "status"] if c in df.columns]
        display = df[cols].copy()
        display.columns = [c.replace("_", " ").title() for c in cols]
        st.dataframe(display, use_container_width=True)
    else:
        st.info("No events uploaded yet.")
except Exception as e:
    st.error(f"Could not load events: {e}")
