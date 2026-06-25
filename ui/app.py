import os
import requests
import streamlit as st
import pandas as pd

API_BASE = "http://api:8000"

st.set_page_config(
    page_title="Event Manager",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom logo at the top of the sidebar
_ICON_PATH = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
if os.path.exists(_ICON_PATH):
    st.logo(_ICON_PATH)


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


def _build_event_context() -> str:
    """
    Build a structured [EVENT CONTEXT] block from the uploaded draft stored in session state.
    Injected into every chat message so the agent never has to ask for details.
    """
    data = st.session_state.get("venue_results")
    if not data:
        return ""
    reqs = data.get("event_requirements") or {}
    collection = data.get("event_collection", "event_management")
    lines = [
        "[EVENT CONTEXT — user has already uploaded an event brief. Use this information directly.]",
        f"Collection: {collection}",
    ]
    if reqs.get("city"):
        lines.append(f"City: {reqs['city']}")
    if reqs.get("postcode"):
        lines.append(f"Postcode: {reqs['postcode']}")
    if reqs.get("attendees"):
        lines.append(f"Attendees: {reqs['attendees']}")
    if reqs.get("min_budget") or reqs.get("max_budget"):
        lines.append(f"Budget: £{reqs.get('min_budget', 0):,.0f} – £{reqs.get('max_budget', 0):,.0f}")
    if reqs.get("event_date"):
        lines.append(f"Event date: {reqs['event_date']}")
    if reqs.get("food_required"):
        lines.append("Food/catering: Required")
    if reqs.get("food_categories"):
        lines.append(f"Dietary categories: {', '.join(reqs['food_categories'])}")
    if reqs.get("hotel_required"):
        lines.append("Hotel accommodation: Required")
    if reqs.get("additional_requirements"):
        extras = reqs["additional_requirements"]
        if isinstance(extras, list):
            lines.append(f"Additional requirements: {', '.join(extras)}")
    # Vendor intel
    vendor_data = st.session_state.get("vendor_results")
    if vendor_data and vendor_data.get("filtered_count", 0) > 0:
        lines.append(
            f"Vendor search results available in ChromaDB vendor_intel collection: "
            f"{vendor_data['caterers_found']} caterers, {vendor_data['hotels_found']} hotels "
            f"near {vendor_data.get('postcode', reqs.get('postcode', ''))}."
        )
    lines.append(
        "INSTRUCTION: Do NOT ask the user for event details. "
        "Call search_event_requirements and search_nearby_vendors to answer based on this indexed data."
    )
    return "\n".join(lines)


def _call_chat_api(message: str, knowledge_source: str, history: list, evaluate: bool = False) -> dict:
    try:
        event_context = _build_event_context()
        payload = {
            "message": message,
            "knowledge_source": knowledge_source,
            "history": history,
            "event_context": event_context or None,
            "evaluate": evaluate,
        }
        resp = requests.post(f"{API_BASE}/api/chat", json=payload, timeout=180)
        if resp.status_code == 200:
            return resp.json()
        return {"answer": f"API error {resp.status_code}: {resp.text}", "sources": [], "knowledge_source": knowledge_source, "ragas_metrics": None}
    except Exception as exc:
        return {"answer": f"Error: {exc}", "sources": [], "knowledge_source": knowledge_source, "ragas_metrics": None}


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


# ─── RAGAS Metrics Renderer ───────────────────────────────────────────────────

def _render_ragas_metrics(metrics: dict):
    """Render RAGAS evaluation scores as a compact panel inside a chat message."""
    if not metrics:
        return
    if metrics.get("error") and metrics["error"] not in ("no_contexts",):
        st.caption(f"RAGAS: evaluation error — {metrics['error']}")
        return
    if metrics.get("error") == "no_contexts":
        st.caption("RAGAS: no retrieved contexts to evaluate (direct knowledge answer)")
        return

    faith = metrics.get("faithfulness")
    rel   = metrics.get("answer_relevancy")

    with st.container(border=True):
        st.caption("**RAGAS Evaluation**")
        col1, col2 = st.columns(2)

        with col1:
            if faith is not None:
                st.metric(
                    label="Faithfulness",
                    value=f"{faith:.0%}",
                    help="How grounded is the answer in the retrieved chunks? "
                         "High = answer stays close to what was retrieved.",
                )
                st.progress(float(faith))
            else:
                st.caption("Faithfulness: n/a")

        with col2:
            if rel is not None:
                st.metric(
                    label="Answer Relevancy",
                    value=f"{rel:.0%}",
                    help="How relevant is the answer to the question? "
                         "High = answer directly addresses what was asked.",
                )
                st.progress(float(rel))
            else:
                st.caption("Answer Relevancy: n/a")


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

# ─── Sidebar — RAGAS toggle (persists across tab switches) ────────────────────
with st.sidebar:
    st.divider()
    st.subheader("Evaluation")
    ragas_enabled = st.toggle(
        "Enable RAGAS Evaluation",
        value=False,
        key="ragas_enabled",
        help=(
            "After each chat reply, runs RAGAS to score:\n"
            "- **Faithfulness** — is the answer grounded in retrieved chunks?\n"
            "- **Answer Relevancy** — does the answer address the question?\n\n"
            "Adds ~10–30 s per reply (extra LLM calls)."
        ),
    )
    if ragas_enabled:
        st.info("RAGAS active — metrics will appear below each reply.")


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

    # ── Draft management helpers ──────────────────────────────────────────────
    def _fetch_drafts() -> list:
        try:
            resp = requests.get(f"{API_BASE}/api/event/drafts", timeout=10)
            return resp.json() if resp.status_code == 200 else []
        except Exception:
            return []

    def _load_draft(draft_id: str):
        try:
            resp = requests.get(f"{API_BASE}/api/event/drafts/{draft_id}", timeout=15)
            return resp.json() if resp.status_code == 200 else None
        except Exception:
            return None

    def _delete_draft(draft_id: str) -> bool:
        try:
            resp = requests.delete(f"{API_BASE}/api/event/drafts/{draft_id}", timeout=10)
            return resp.status_code == 204
        except Exception:
            return False

    if "active_draft_id" not in st.session_state:
        st.session_state["active_draft_id"] = None

    # ── Saved Drafts Section ──────────────────────────────────────────────────
    saved_drafts = _fetch_drafts()
    active_id = st.session_state.get("active_draft_id")

    if saved_drafts:
        # Active draft banner
        if active_id:
            active_meta = next((d for d in saved_drafts if d["draft_id"] == active_id), None)
            if active_meta:
                banner_col, clear_col = st.columns([6, 1])
                with banner_col:
                    parts = []
                    if active_meta.get("city"):       parts.append(f"📍 {active_meta['city']}")
                    if active_meta.get("postcode"):   parts.append(active_meta["postcode"])
                    if active_meta.get("event_date"): parts.append(f"📅 {active_meta['event_date']}")
                    if active_meta.get("attendees"):  parts.append(f"👥 {active_meta['attendees']} attendees")
                    if active_meta.get("max_budget"): parts.append(f"£{float(active_meta['max_budget'] or 0):,.0f} budget")
                    st.success(
                        f"**Active draft:** {active_meta['filename']}  \n"
                        + "  ·  ".join(parts)
                    )
                with clear_col:
                    st.write("")
                    if st.button("✖ Deselect", key="deselect_draft_btn"):
                        st.session_state["active_draft_id"] = None
                        st.session_state.venue_results = None
                        st.session_state["vendor_results"] = None
                        st.rerun()

        with st.expander(
            f"📂 Saved Drafts ({len(saved_drafts)})" +
            (" — click to switch draft" if active_id else " — select a draft to load"),
            expanded=not bool(active_id),
        ):
            for d in saved_drafts:
                is_active = d["draft_id"] == active_id
                row_c, use_c, del_c = st.columns([6, 1, 1])
                with row_c:
                    label = ("✅ " if is_active else "") + d["filename"]
                    st.markdown(f"**{label}**")
                    meta = []
                    if d.get("city"):       meta.append(f"📍 {d['city']}")
                    if d.get("postcode"):   meta.append(d["postcode"])
                    if d.get("event_date"): meta.append(f"📅 {d['event_date']}")
                    if d.get("attendees"):  meta.append(f"👥 {d['attendees']}")
                    if d.get("max_budget"): meta.append(f"£{float(d['max_budget'] or 0):,.0f}")
                    if d.get("created_at"): meta.append(f"🕐 {d['created_at'][:10]}")
                    st.caption("  ·  ".join(meta))
                with use_c:
                    if st.button(
                        "Active" if is_active else "Use",
                        key=f"use_draft_{d['draft_id']}",
                        disabled=is_active,
                        type="primary",
                    ):
                        with st.spinner("Loading draft…"):
                            full = _load_draft(d["draft_id"])
                        if full:
                            st.session_state.venue_results = full
                            st.session_state["active_draft_id"] = d["draft_id"]
                            st.session_state.chat_histories["event_management"] = []
                            st.rerun()
                        else:
                            st.error("Could not load draft.")
                with del_c:
                    if st.button("Delete", key=f"del_draft_{d['draft_id']}"):
                        if _delete_draft(d["draft_id"]):
                            if d["draft_id"] == active_id:
                                st.session_state["active_draft_id"] = None
                                st.session_state.venue_results = None
                                st.session_state["vendor_results"] = None
                            st.rerun()
                        else:
                            st.error("Delete failed.")

        st.divider()

    # ── Upload / Submit a New Draft ───────────────────────────────────────────
    has_active = bool(st.session_state.get("venue_results"))
    with st.expander("📤 Upload New Event Brief", expanded=not has_active):
        st.subheader("Submit Event Requirements")

        # Postcode + radius — drives the local vendor/hotel scrape
        pc_col, rad_col = st.columns([2, 3])
        event_postcode = pc_col.text_input(
            "Event postcode *",
            placeholder="e.g. M1 1AE",
            help="UK postcode of the venue / event location. Used to find nearby caterers and hotels.",
        )
        search_radius = rad_col.slider(
            "Vendor search radius (km)", min_value=1, max_value=100, value=5,
            help=(
                "How far from the postcode to search. "
                "Vendors beyond 10 km are flagged as delivery-only. "
                "Max 100 km."
            ),
        )

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
                    st.session_state["active_draft_id"] = result.get("event_id")
                    st.session_state.chat_histories["event_management"] = []
                    st.success("Venues found! Draft saved — it will be available next time you open the app.")
                    if result.get("event_collection"):
                        st.info(
                            f"Your event requirements are indexed in **{result['event_collection']}**. "
                            "Switch to the **Chat** tab and select **Event Requirements** to ask follow-up questions."
                        )
                    st.rerun()

    # Postcode/radius are defined inside the expander widget code, so they're always
    # available (Streamlit runs collapsed expander code too). But if the expander was
    # collapsed and the user never typed anything, fall back to the active draft's postcode.
    _active_reqs = (st.session_state.get("venue_results") or {}).get("event_requirements") or {}
    if not event_postcode:
        event_postcode = _active_reqs.get("postcode", "")

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

        if not venues:
            st.info(
                "**No pre-indexed venues found for this city.**  \n"
                "The venue knowledge base doesn't have listings for every UK city yet. "
                "Use the **Find Local Caterers & Hotels** section below to run a live web search "
                "that scrapes real venues and hotels near your event postcode in real time."
            )
        else:
            fallback_count = sum(1 for v in venues if v.get("is_fallback"))
            wrong_city = [
                v for v in venues
                if v.get("city", "").lower() not in (reqs.get("city", "").lower() or "zzzz")
                and reqs.get("city", "")
            ]
            if wrong_city:
                # Shouldn't happen after the guardrail fix — but surface it loudly if it does
                st.error(
                    f"Location guardrail warning: {len(wrong_city)} venue(s) from wrong city "
                    "detected and hidden. Please report this."
                )
                venues = [v for v in venues if v not in wrong_city]

            if fallback_count > 0 and venues:
                st.warning(
                    f"Showing {len(venues)} venues with relaxed constraints "
                    f"(no exact matches in {reqs.get('city', 'your city')})."
                )

            if venues:
                st.subheader(f"Recommended Venues ({len(venues)})")
                _render_venue_grid(venues)

        # ── Local Vendor & Hotel Finder (live web scraper — primary for hotels) ─
        st.divider()
        st.subheader("Find Local Caterers & Hotels")

        if not event_postcode:
            st.info("Enter an **event postcode** above to enable proximity-based vendor search.")
        else:
            reqs_v = data.get("event_requirements", {})
            food_required  = bool(reqs_v.get("food_required", True))
            hotel_required = bool(reqs_v.get("hotel_required", True))
            max_budget     = float(reqs_v.get("max_budget", 0) or 0)
            attendees      = int(reqs_v.get("attendees", 0) or 0)
            food_cats      = reqs_v.get("food_categories", []) or []

            # Controls row
            fc1, fc2, fc3 = st.columns(3)
            food_required  = fc1.checkbox("Caterers / food vendors", value=food_required)
            hotel_required = fc2.checkbox("Hotels / accommodation",  value=hotel_required)
            active_radius  = fc3.slider(
                "Radius (km)", min_value=1, max_value=100,
                value=int(search_radius),
                key="vendor_radius_active",
                help="Vendors beyond 10 km will be marked as delivery-only.",
            )

            st.caption(
                f"**How it works:** DuckDuckGo searches the web for '{event_postcode}' vendors → "
                "discovers their websites automatically → scrapes each page → "
                "OSM map data fills in geo-location → pipeline filters by radius, budget & diet → "
                "results are indexed in ChromaDB for the chat agent."
            )

            if st.button("🌐 Search Web + Map for Nearby Vendors", type="primary",
                         use_container_width=True, key="find_vendors_btn"):
                with st.spinner(
                    f"Searching web + OSM within {active_radius} km of {event_postcode} "
                    f"— this may take 30–90 s…"
                ):
                    try:
                        payload = {
                            "postcode":        event_postcode.strip(),
                            "city":            reqs_v.get("city", ""),
                            "attendees":       attendees,
                            "total_budget":    max_budget,
                            "radius_km":       float(active_radius),
                            "food_required":   food_required,
                            "hotel_required":  hotel_required,
                            "food_categories": food_cats,
                            "event_id":        data.get("event_id"),
                        }
                        # Persist so the retry button can reuse it on the next render
                        st.session_state["vendor_last_payload"] = payload
                        resp = requests.post(
                            f"{API_BASE}/api/v1/vendors/scrape-for-event",
                            json=payload,
                            timeout=180,
                        )
                        if resp.status_code == 200:
                            vdata = resp.json()
                            st.session_state["vendor_results"] = vdata
                            st.session_state["vendor_search_radius"] = active_radius
                        else:
                            err = resp.json().get("detail", resp.text)
                            st.error(f"Vendor search failed: {err}")
                    except Exception as exc:
                        st.error(f"Connection error: {exc}")

            vdata = st.session_state.get("vendor_results")

            if vdata:
                used_radius = st.session_state.get("vendor_search_radius", active_radius)
                total_found = vdata.get("filtered_count", 0)

                # ── No results → suggest nearby towns or widen radius ─────────
                if total_found == 0:
                    st.warning(
                        f"No verified vendors found within **{used_radius} km** of "
                        f"**{event_postcode}**.\n\n"
                        "Results from other cities (Manchester, London, etc.) have been "
                        "filtered out by the location guardrail — only vendors confirmed "
                        "in your event area are shown."
                    )

                    nearby_towns = vdata.get("nearby_towns", [])
                    if nearby_towns:
                        st.subheader("📍 Nearby towns with potential vendors")
                        st.caption(
                            "These towns are close to your event postcode. "
                            "Select one or more to search for vendors there."
                        )
                        town_options = {
                            f"{t['town']} ({t['outcode']}) — {t['distance_km']} km away": t
                            for t in nearby_towns
                        }
                        selected_labels = st.multiselect(
                            "Select nearby towns to include in vendor search:",
                            options=list(town_options.keys()),
                            key="nearby_towns_select",
                        )
                        if selected_labels and st.button(
                            "🔍 Search selected towns for vendors",
                            key="search_nearby_towns_btn",
                            type="primary",
                        ):
                            # Run one search per selected town and aggregate
                            all_results = []
                            for label in selected_labels:
                                town_info = town_options[label]
                                town_postcode = town_info["postcode_example"]
                                with st.spinner(f"Searching {town_info['town']}…"):
                                    try:
                                        tp = dict(st.session_state.get("vendor_last_payload", {}))
                                        tp["postcode"] = town_postcode
                                        tp["city"] = town_info["town"]
                                        tp["radius_km"] = float(used_radius)
                                        r = requests.post(
                                            f"{API_BASE}/api/v1/vendors/scrape-for-event",
                                            json=tp, timeout=180,
                                        )
                                        if r.status_code == 200:
                                            all_results.append(r.json())
                                    except Exception as exc:
                                        st.error(f"Error searching {town_info['town']}: {exc}")

                            if all_results:
                                # Merge results — use the last one as base (indexing is cumulative)
                                merged = all_results[-1]
                                total_c = sum(r.get("caterers_found", 0) for r in all_results)
                                total_h = sum(r.get("hotels_found", 0)   for r in all_results)
                                merged["caterers_found"] = total_c
                                merged["hotels_found"]   = total_h
                                merged["filtered_count"] = total_c + total_h
                                merged["top_caterers"] = [
                                    v for r in all_results for v in r.get("top_caterers", [])
                                ][:15]
                                merged["top_hotels"] = [
                                    v for r in all_results for v in r.get("top_hotels", [])
                                ][:15]
                                st.session_state["vendor_results"] = merged
                                st.rerun()

                    # Radius expansion as a secondary option
                    if used_radius < 100:
                        st.divider()
                        st.caption("Or widen the radius to find more options:")
                        expand_min = min(used_radius + 1, 99)
                        expand_default = min(used_radius * 2, 100)
                        new_radius = st.slider(
                            "Search radius (km):",
                            min_value=expand_min,
                            max_value=100,
                            value=max(expand_default, expand_min),
                            key="expand_radius_slider",
                        )
                        if st.button("🔁 Retry with wider radius", key="retry_wider_btn"):
                            with st.spinner(f"Retrying with {new_radius} km radius…"):
                                try:
                                    retry_payload = dict(st.session_state.get("vendor_last_payload", {}))
                                    retry_payload["radius_km"] = float(new_radius)
                                    resp = requests.post(
                                        f"{API_BASE}/api/v1/vendors/scrape-for-event",
                                        json=retry_payload, timeout=180,
                                    )
                                    if resp.status_code == 200:
                                        st.session_state["vendor_results"] = resp.json()
                                        st.session_state["vendor_search_radius"] = new_radius
                                        st.session_state["vendor_last_payload"] = retry_payload
                                        st.rerun()
                                    else:
                                        st.error(resp.json().get("detail", resp.text))
                                except Exception as exc:
                                    st.error(f"Retry failed: {exc}")
                    else:
                        st.error(
                            "Already at 100 km radius with no results. "
                            "Try selecting a nearby town above."
                        )
                else:
                    # ── Metrics row ───────────────────────────────────────────
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Total vendors", total_found)
                    m2.metric("Caterers", vdata.get("caterers_found", 0))
                    m3.metric("Hotels",   vdata.get("hotels_found", 0))
                    m4.metric("Indexed",  vdata.get("indexed", 0))
                    delivery_count = sum(
                        1 for v in vdata.get("top_caterers", []) + vdata.get("top_hotels", [])
                        if v.get("delivery_available")
                    )
                    m5.metric("Delivery-capable", delivery_count)

                    st.caption(
                        f"Radius **{used_radius} km** · "
                        f"{vdata.get('raw_count', 0)} raw → "
                        f"{total_found} after guardrails · "
                        "Vendors >10 km are flagged as delivery-only."
                    )

                    def _render_vendor_df(records: list, label: str, icon: str):
                        if not records:
                            return
                        df = pd.DataFrame(records)
                        df.columns = [c.replace("_", " ").title() for c in df.columns]
                        # Put delivery flag prominently
                        if "Delivery Available" in df.columns:
                            df["Delivery Available"] = df["Delivery Available"].map(
                                {True: "Yes 🚚", False: "In-person"}
                            )
                        with st.expander(f"{icon} {label}", expanded=True):
                            st.dataframe(df, use_container_width=True)

                    _render_vendor_df(
                        vdata.get("top_caterers", []),
                        f"Caterers ({vdata.get('caterers_found', 0)} found)",
                        "🍽️"
                    )
                    _render_vendor_df(
                        vdata.get("top_hotels", []),
                        f"Hotels ({vdata.get('hotels_found', 0)} found)",
                        "🏨"
                    )

                    st.success(
                        "✅ Results indexed. Chat with your AI assistant: "
                        "*'Which caterers near my event offer halal delivery?'* or "
                        "*'What hotels are within 5 km?'*"
                    )


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

    # ── Draft context banner (shown for ALL knowledge sources) ───────────────
    event_data = st.session_state.get("venue_results")
    if event_data:
        reqs_banner = event_data.get("event_requirements") or {}
        city_b   = reqs_banner.get("city", "")
        pc_b     = reqs_banner.get("postcode", "")
        att_b    = reqs_banner.get("attendees", "")
        bud_b    = reqs_banner.get("max_budget", "")
        coll_b   = event_data.get("event_collection", "event_management")
        vendor_b = st.session_state.get("vendor_results")
        vendor_note = ""
        if vendor_b and vendor_b.get("filtered_count", 0) > 0:
            vendor_note = (
                f" · **{vendor_b['caterers_found']}** caterers & "
                f"**{vendor_b['hotels_found']}** hotels indexed"
            )
        st.success(
            f"📄 **Draft linked** — {city_b or 'Event'} ({pc_b}) · "
            f"{att_b} attendees · £{float(bud_b or 0):,.0f} budget · "
            f"Collection: `{coll_b}`{vendor_note}  \n"
            "The AI already has your event details — just ask your question directly."
        )

    st.divider()

    # ── Chat Interface ────────────────────────────────────────────────────────
    # Each source maintains its own history
    current_history: list = st.session_state.chat_histories.get(source, [])

    # Display existing history for this source (including any stored RAGAS metrics)
    for msg in current_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("ragas_metrics"):
                _render_ragas_metrics(msg["ragas_metrics"])

    user_input = st.chat_input(
        "Ask a question about venues or your event…",
        key="chat_input_field",
    )

    if user_input:
        # Snapshot history (role+content only) before appending the new message
        prev_history = [{"role": m["role"], "content": m["content"]} for m in current_history]

        # Show user message immediately
        current_history.append({"role": "user", "content": user_input, "ragas_metrics": None})
        with st.chat_message("user"):
            st.write(user_input)

        # Call API with conversation history
        ragas_flag = st.session_state.get("ragas_enabled", False)
        with st.chat_message("assistant"):
            spinner_msg = "Thinking… (+ RAGAS evaluation)" if ragas_flag else "Thinking…"
            with st.spinner(spinner_msg):
                reply = _call_chat_api(user_input, source, prev_history, evaluate=ragas_flag)
            st.write(reply["answer"])
            if reply.get("sources"):
                st.caption(f"Sources: {', '.join(reply['sources'])}")
            if reply.get("ragas_metrics"):
                _render_ragas_metrics(reply["ragas_metrics"])

        current_history.append({
            "role": "assistant",
            "content": reply["answer"],
            "ragas_metrics": reply.get("ragas_metrics"),
        })

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
