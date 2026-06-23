import requests
import streamlit as st

API_BASE = "http://api:8000"

st.set_page_config(
    page_title="Event Manager",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ─── API Helpers ──────────────────────────────────────────────────────────────

def _call_upload_api(file, text):
    try:
        if file:
            files = {"file": (file.name, file.getvalue(), file.type)}
            resp = requests.post(f"{API_BASE}/api/event/upload", files=files, timeout=180)
        else:
            resp = requests.post(
                f"{API_BASE}/api/event/upload",
                data={"text": text},
                timeout=180,
            )
        if resp.status_code == 200:
            return resp.json()
        detail = resp.json().get("detail", resp.text)
        st.error(f"API error {resp.status_code}: {detail}")
        return None
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the API. Make sure the backend is running.")
        return None
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
        return None


def _call_chat_api(message: str, knowledge_source: str, history: list) -> dict:
    try:
        payload = {
            "message": message,
            "knowledge_source": knowledge_source,
            "history": history,
        }
        resp = requests.post(f"{API_BASE}/api/chat", json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()
        return {"answer": f"API error {resp.status_code}: {resp.text}", "sources": [], "knowledge_source": knowledge_source}
    except Exception as exc:
        return {"answer": f"Error: {exc}", "sources": [], "knowledge_source": knowledge_source}


def _call_reindex_api(full: bool = False) -> dict:
    try:
        resp = requests.post(
            f"{API_BASE}/api/index/reindex",
            params={"full": str(full).lower()},
            timeout=120,
        )
        return resp.json() if resp.status_code == 200 else {"error": resp.text, "status": "failed"}
    except Exception as exc:
        return {"error": str(exc), "status": "failed"}


def _call_stats_api() -> dict:
    try:
        resp = requests.get(f"{API_BASE}/api/index/stats", timeout=30)
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


def _call_health_api() -> dict:
    try:
        resp = requests.get(f"{API_BASE}/api/index/health", timeout=30)
        return resp.json() if resp.status_code == 200 else {"status": "error"}
    except Exception as exc:
        return {"status": "unreachable", "detail": str(exc)}


# ─── Venue Card Rendering ─────────────────────────────────────────────────────

def _render_venue_card(venue: dict):
    is_fallback = venue.get("is_fallback", False)
    with st.container(border=True):
        if venue.get("venue_image"):
            try:
                st.image(venue["venue_image"], use_column_width=True)
            except Exception:
                pass

        title = venue.get("venue_name", "Unknown Venue")
        label = " ⚡ Alternative" if is_fallback else ""
        st.subheader(f"{title}{label}")

        location = venue.get("city", "Unknown")
        if venue.get("postcode"):
            location += f", {venue['postcode']}"
        st.caption(f"📍 {location}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Capacity", venue.get("capacity", "—"))
        m2.metric("Budget", venue.get("budget_compatibility", "—"))
        score = venue.get("match_score", 0)
        m3.metric("Match", f"{score:.0f}/100")
        st.progress(min(score / 100.0, 1.0))

        # Score breakdown
        bd = venue.get("score_breakdown", {})
        if bd:
            with st.expander("Score Breakdown"):
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("Capacity", f"{bd.get('capacity_score', 0):.0f}")
                c2.metric("Budget", f"{bd.get('budget_score', 0):.0f}")
                c3.metric("Location", f"{bd.get('location_score', 0):.0f}")
                c4.metric("Evt Type", f"{bd.get('event_type_score', 0):.0f}")
                c5.metric("Features", f"{bd.get('feature_score', 0):.0f}")
                c6.metric("Business", f"{bd.get('business_score', 0):.0f}")

        desc = venue.get("venue_description", "")
        if desc:
            st.write(desc[:280] + ("…" if len(desc) > 280 else ""))

        features = venue.get("venue_features", [])
        if features:
            st.write("**Features:** " + " · ".join(features[:5]))

        badges = []
        if venue.get("parking") is True:
            badges.append("🅿️ Parking")
        if venue.get("wifi") is True:
            badges.append("📶 WiFi")
        if venue.get("av_equipment") is True:
            badges.append("🎥 AV")
        if venue.get("catering") is True:
            badges.append("🍽️ Catering")
        if venue.get("wheelchair_access") is True:
            badges.append("♿ Accessible")
        if venue.get("hybrid_events") is True:
            badges.append("💻 Hybrid")
        if venue.get("outdoor_space") is True:
            badges.append("🌿 Outdoor")
        if badges:
            st.write(" ".join(badges))

        if venue.get("nearest_train"):
            st.caption(f"🚂 {venue['nearest_train']}")

        reason = venue.get("recommendation_reason", "")
        if reason:
            st.info(f"**Why this venue?** {reason}")

        if venue.get("venue_url"):
            st.markdown(f"[View venue website]({venue['venue_url']})")


def _render_venue_grid(venues: list):
    for row_start in range(0, len(venues), 3):
        cols = st.columns(3)
        for col_idx, venue in enumerate(venues[row_start: row_start + 3]):
            with cols[col_idx]:
                _render_venue_card(venue)


# ─── Session State Init ───────────────────────────────────────────────────────

if "venue_results" not in st.session_state:
    st.session_state.venue_results = None

if "chat_histories" not in st.session_state:
    st.session_state.chat_histories = {
        "venue_master": [],
        "event_management": [],
    }

if "index_stats" not in st.session_state:
    st.session_state.index_stats = {}

# ─── Navigation ───────────────────────────────────────────────────────────────

tab_index, tab_events, tab_chat = st.tabs([
    "📦 Indexing",
    "🏢 Event Manager",
    "💬 Chat",
])


# ════════════════════════════════════════════════════════════════
# TAB 1 – INDEXING
# ════════════════════════════════════════════════════════════════
with tab_index:
    st.title("Venue Index Management")
    st.write(
        "Manage the **venue_master** knowledge base. "
        "Venue data is sourced from Canvas API and automatically refreshed daily at 04:00 UTC."
    )

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔄 Reindex Now", type="primary", use_container_width=True, key="reindex_btn"):
            with st.spinner("Running incremental reindex…"):
                result = _call_reindex_api(full=False)
            if result.get("status") == "ok":
                st.success(
                    f"Reindex complete — "
                    f"{result.get('new_venues', 0)} new · "
                    f"{result.get('updated_venues', 0)} updated · "
                    f"{result.get('removed_venues', 0)} removed"
                )
                st.session_state.index_stats = result
            else:
                st.error(f"Reindex failed: {result.get('error', 'Unknown error')}")

    with col_b:
        if st.button("📊 Refresh Statistics", use_container_width=True, key="stats_btn"):
            with st.spinner("Loading…"):
                stats = _call_stats_api()
            if stats:
                st.session_state.index_stats = stats
                st.success("Statistics refreshed")
            else:
                st.warning("Could not load statistics")

    with col_c:
        if st.button("🏥 Collection Health Check", use_container_width=True, key="health_btn"):
            with st.spinner("Checking…"):
                health = _call_health_api()
            status = health.get("status", "unknown")
            if status == "healthy":
                st.success(f"Healthy — {health.get('chunk_count', 0)} chunks in venue_master")
            elif status == "empty":
                st.warning("Collection is empty. Click Reindex Now to populate.")
            else:
                st.error(f"Issue: {health.get('detail', status)}")

    st.divider()
    st.subheader("Collection Statistics")

    cached = st.session_state.index_stats
    if not cached:
        cached = _call_stats_api()
        if cached:
            st.session_state.index_stats = cached

    if cached:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Venues", cached.get("total_venues", 0))
        m2.metric("Total Chunks", cached.get("live_chunk_count", cached.get("total_chunks", 0)))
        last_idx = (cached.get("last_indexed_at") or "Never")
        m3.metric("Last Indexed", last_idx[:19] if last_idx != "Never" else "Never")
        next_run = (cached.get("next_scheduled_indexing") or "Unknown")
        m4.metric("Next Scheduled", next_run[:19] if next_run != "Unknown" else "Unknown")

        c1, c2, c3 = st.columns(3)
        c1.metric("New (last run)", cached.get("new_venues", 0))
        c2.metric("Updated (last run)", cached.get("updated_venues", 0))
        c3.metric("Removed (last run)", cached.get("removed_venues", 0))
    else:
        st.info("Click **Refresh Statistics** to load collection data.")

    with st.expander("Advanced — Full Reindex"):
        st.warning("Wipes the entire collection and rebuilds from scratch. Use with caution.")
        if st.button("⚠️ Full Reindex (Wipe & Rebuild)", use_container_width=True, key="full_reindex_btn"):
            with st.spinner("Running full reindex…"):
                result = _call_reindex_api(full=True)
            if result.get("status") == "ok":
                st.success(
                    f"Full reindex complete — "
                    f"{result.get('total_venues', 0)} venues · "
                    f"{result.get('total_chunks', 0)} chunks"
                )
                st.session_state.index_stats = result
            else:
                st.error(f"Failed: {result.get('error', 'Unknown error')}")


# ════════════════════════════════════════════════════════════════
# TAB 2 – CORPORATE EVENT MANAGEMENT
# ════════════════════════════════════════════════════════════════
with tab_events:
    st.title("Event Manager")
    st.write(
        "Submit your event requirements to receive AI-powered venue recommendations. "
        "Your event will also be indexed so you can ask questions in the **Chat** tab."
    )

    st.header("Submit Event Requirements")

    input_method = st.radio(
        "Input method:",
        ["📁 Upload File (PDF / Word)", "✏️ Enter Text"],
        horizontal=True,
        key="event_input_method",
    )

    uploaded_file = None
    event_text = None

    if input_method == "📁 Upload File (PDF / Word)":
        uploaded_file = st.file_uploader(
            "Upload your event brief",
            type=["pdf", "doc", "docx"],
            key="event_uploader",
        )
        if uploaded_file:
            st.success(f"Uploaded: **{uploaded_file.name}**")
    else:
        event_text = st.text_area(
            "Event requirements",
            height=220,
            placeholder=(
                "Example:\n"
                "Corporate conference in London for 250 guests.\n"
                "Date: 20th September 2026, 9am – 6pm.\n"
                "Budget: £8,000 – £18,000.\n"
                "Requirements: AV equipment, breakout rooms, catering, parking."
            ),
            key="event_text_area",
        )

    if st.button("🔍 Find Venues", type="primary", use_container_width=True, key="find_venues_btn"):
        if not uploaded_file and not event_text:
            st.error("Please provide event requirements via file upload or text input.")
        else:
            with st.spinner("AI agent is analysing requirements and finding venues — 30–60 s…"):
                result = _call_upload_api(uploaded_file, event_text)
            if result:
                st.session_state.venue_results = result
                # Reset event chat history so it reflects the new event
                st.session_state.chat_histories["event_management"] = []
                st.success("Venues found! See recommendations below.")
                if result.get("event_collection"):
                    st.info(
                        f"Your event requirements are indexed in **{result['event_collection']}**. "
                        "Switch to the **Chat** tab and select **Event Requirements** to ask follow-up questions."
                    )

    # ── Venue Recommendation Dashboard ───────────────────────────────────────
    if st.session_state.venue_results:
        data = st.session_state.venue_results
        reqs = data.get("event_requirements", {})
        venues = data.get("recommended_venues", [])
        summary = data.get("summary", {})
        agent_response = data.get("agent_response", "")

        st.divider()
        st.header("Venue Recommendations")

        with st.expander("Extracted Event Requirements", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("City", reqs.get("city") or "Any")
            c2.metric("Attendees", reqs.get("attendees") or "—")
            c3.metric("Min Budget", f"£{reqs['min_budget']:,.0f}" if reqs.get("min_budget") else "—")
            c4.metric("Max Budget", f"£{reqs['max_budget']:,.0f}" if reqs.get("max_budget") else "—")
            if reqs.get("event_date"):
                st.write(f"**Date:** {reqs['event_date']}")
            if reqs.get("additional_requirements"):
                st.write(f"**Additional:** {', '.join(reqs['additional_requirements'])}")

        if agent_response:
            with st.expander("AI Agent Analysis"):
                st.write(agent_response)

        if summary:
            s1, s2 = st.columns(2)
            with s1:
                st.metric("Total Venues", summary.get("total_venues", 0))
                st.metric("Best Match", summary.get("best_venue", "—"))
            with s2:
                st.info(f"**Budget:** {summary.get('budget_analysis', '')}")
                st.info(f"**Capacity:** {summary.get('capacity_analysis', '')}")
            for rec in summary.get("key_recommendations", []):
                st.write(f"• {rec}")

        fallback_count = sum(1 for v in venues if v.get("is_fallback"))
        if fallback_count > 0:
            st.warning(f"No exact matches — showing {len(venues)} closest alternatives with relaxed constraints.")

        if not venues:
            st.warning("No venues matched. Try adjusting budget or location.")
        else:
            st.subheader(f"Recommended Venues ({len(venues)})")
            _render_venue_grid(venues)


# ════════════════════════════════════════════════════════════════
# TAB 3 – CHAT
# ════════════════════════════════════════════════════════════════
with tab_chat:
    st.title("Event Manager Chat")
    st.write("Chat with the venue knowledge base or your uploaded event requirements.")

    # ── Knowledge Source Selector ─────────────────────────────────────────────
    st.subheader("Knowledge Source")
    source = st.radio(
        "What do you want to chat about?",
        ["venue_master", "event_management"],
        format_func=lambda x: (
            "🏛️  Venue Knowledge Base (venue_master)"
            if x == "venue_master"
            else "📋  Event Requirements (event_management)"
        ),
        horizontal=True,
        key="chat_knowledge_source",
    )

    # Context hint per source
    if source == "venue_master":
        st.info(
            "**Venue Knowledge Base** — Ask about any venue in the Canvas index.\n\n"
            "Examples: *Which venues in London have AV equipment?* · "
            "*Compare conference venues for 300 guests* · "
            "*Show venues with parking and outdoor space*"
        )
    else:
        has_event = bool(st.session_state.venue_results)
        if has_event:
            st.info(
                "**Event Requirements** — Ask about your uploaded event and get matched venue suggestions.\n\n"
                "Examples: *What is my approved budget?* · "
                "*Suggest venues that fit my requirements* · "
                "*Which recommended venue has the highest match score?*"
            )
        else:
            st.warning(
                "No event requirements indexed yet. "
                "Go to **Event Manager** and submit your event brief first, "
                "then return here to ask questions about your specific event."
            )

    st.divider()

    # ── Chat Interface ────────────────────────────────────────────────────────
    # Each source maintains its own history
    current_history: list = st.session_state.chat_histories.get(source, [])

    # Display existing history for this source
    for msg in current_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_input = st.chat_input(
        "Ask a question about venues or your event…",
        key="chat_input_field",
    )

    if user_input:
        # Snapshot history before appending the new message
        prev_history = [{"role": m["role"], "content": m["content"]} for m in current_history]

        # Show user message immediately
        current_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        # Call API with conversation history
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = _call_chat_api(user_input, source, prev_history)
            st.write(reply["answer"])
            if reply.get("sources"):
                st.caption(f"Sources: {', '.join(reply['sources'])}")

        current_history.append({"role": "assistant", "content": reply["answer"]})

        # Persist per-source history
        st.session_state.chat_histories[source] = current_history

    # Clear history button for current source
    if current_history:
        if st.button(
            f"Clear {source.replace('_', ' ').title()} Chat History",
            key=f"clear_history_{source}",
        ):
            st.session_state.chat_histories[source] = []
            st.rerun()
