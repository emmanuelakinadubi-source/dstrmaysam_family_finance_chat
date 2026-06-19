import streamlit as st
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ui.services import api_client as api

st.set_page_config(page_title="Event Chat", layout="wide")
st.title("💬 Chat with Event Documents")
st.markdown("Ask questions about uploaded event plans. The AI retrieves context from your documents.")

EXAMPLE_QUESTIONS = [
    "What is the event budget?",
    "How many attendees are expected?",
    "Is hosting/accommodation required?",
    "What city is the event in?",
    "What food or catering is required?",
    "How many days does the event last?",
    "What are the special requirements?",
]

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Event Scope")
    scope = st.radio("Chat scope", ["All uploaded events", "Specific event"])

    event_id = None
    if scope == "Specific event":
        try:
            events = api.list_events()
            if events:
                opts = {"(select an event)": None}
                opts.update({f"{e['event_name']} — {e.get('city', '')}": e["id"] for e in events})
                sel = st.selectbox("Choose event", list(opts.keys()))
                event_id = opts[sel]
                if event_id and "last_event_id" in st.session_state:
                    st.session_state["last_event_id"] = event_id
            else:
                st.info("No events uploaded yet.")
        except Exception as e:
            st.warning(f"Could not load events: {e}")

    evaluate = st.toggle("RAGAS evaluation", value=False,
                         help="Run RAGAS faithfulness & relevancy scoring (adds latency)")

    st.divider()
    st.subheader("Example Questions")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, key=f"ex_{q}"):
            st.session_state["prefill"] = q

# ── Chat Interface ─────────────────────────────────────────────────────────────
if "event_messages" not in st.session_state:
    st.session_state["event_messages"] = []

for msg in st.session_state["event_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("ragas"):
            r = msg["ragas"]
            st.caption(
                f"RAGAS — Faithfulness: `{r.get('faithfulness', 'N/A')}` · "
                f"Answer Relevancy: `{r.get('answer_relevancy', 'N/A')}`"
            )

prefill = st.session_state.pop("prefill", None)
prompt = st.chat_input("Ask about your event documents...") or prefill

if prompt:
    st.session_state["event_messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching event documents..."):
            try:
                result = api.event_chat(
                    question=prompt,
                    event_id=str(event_id) if event_id else None,
                    evaluate=evaluate,
                )
                answer = result.get("answer", "No answer generated.")
                ragas = result.get("ragas_scores")
                latency = result.get("latency_ms")

                st.markdown(answer)

                meta = []
                if latency:
                    meta.append(f"Latency: `{latency}ms`")
                if meta:
                    st.caption(" · ".join(meta))

                if ragas and not ragas.get("error"):
                    st.caption(
                        f"RAGAS — Faithfulness: `{ragas.get('faithfulness', 'N/A')}` · "
                        f"Answer Relevancy: `{ragas.get('answer_relevancy', 'N/A')}`"
                    )

                if result.get("contexts"):
                    with st.expander("📄 Retrieved context chunks"):
                        for i, ctx in enumerate(result["contexts"], 1):
                            st.markdown(f"**Chunk {i}:** {ctx[:400]}...")

                st.session_state["event_messages"].append({
                    "role": "assistant",
                    "content": answer,
                    "ragas": ragas,
                })

            except Exception as e:
                err = f"Chat error: {e}"
                st.error(err)
                st.session_state["event_messages"].append({"role": "assistant", "content": err})

if st.session_state["event_messages"]:
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state["event_messages"] = []
        st.rerun()
