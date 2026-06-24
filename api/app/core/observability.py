import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_langfuse_enabled: Optional[bool] = None   # resolved once on first call


def _is_enabled() -> bool:
    global _langfuse_enabled
    if _langfuse_enabled is None:
        _langfuse_enabled = bool(
            settings.langfuse_public_key and settings.langfuse_secret_key
        )
        if _langfuse_enabled:
            logger.info("Langfuse observability enabled (host=%s)", settings.langfuse_host)
        else:
            logger.info("Langfuse observability disabled — keys not configured")
    return _langfuse_enabled


def make_langfuse_handler(
    trace_name: str = "agent",
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
):
    """
    Returns a Langfuse LangChain CallbackHandler scoped to a single named trace.
    Uses the Langfuse v4 pattern: create a trace via get_client(), then pass its
    ID as trace_context so LangChain events are nested under it in the dashboard.

    Returns None when LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not set,
    so callers can use `config={"callbacks": [h]} if h else {}` without branching.
    """
    if not _is_enabled():
        return None
    try:
        from langfuse import get_client
        from langfuse.langchain import CallbackHandler

        client = get_client()
        trace_id = client.create_trace_id(seed=session_id)  # deterministic per session

        # Register the trace root with its name and metadata before the LangChain run
        root_span = client.start_observation(
            trace_context={"trace_id": trace_id},
            name=trace_name,
            as_type="chain",
            metadata={**(metadata or {}), "session_id": session_id, "user_id": user_id},
        )

        # Nest all LangChain spans under this root span
        return CallbackHandler(
            trace_context={"trace_id": trace_id, "parent_span_id": root_span.id}
        )
    except Exception as exc:
        logger.warning("Langfuse handler creation failed: %s", exc)
        return None
