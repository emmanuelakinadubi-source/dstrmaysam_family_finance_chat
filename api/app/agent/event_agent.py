import json
import logging
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import AzureChatOpenAI

from app.agent.tools.collection_tool import get_collection_stats
from app.agent.tools.enrichment_tool import enrich_venue_details
from app.agent.tools.event_query_tool import search_event_requirements
from app.agent.tools.extraction_tool import extract_event_requirements
from app.agent.tools.nearby_venue_tool import find_nearby_venues
from app.agent.tools.recommendation_tool import recommend_venues
from app.agent.tools.vendor_intel_tool import search_nearby_vendors
from app.agent.tools.venue_retrieval_tool import search_venues
from app.core.config import settings
from app.core.observability import make_langfuse_handler

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert Corporate Event Planning AI Consultant operating as a unified Event Manager platform.

## Tools:
1. extract_event_requirements — Parse raw text → structured event fields (call FIRST for new event briefs)
2. recommend_venues — Find and rank venues (40/20/15/10/10/5 scoring). Call after extraction.
3. find_nearby_venues — Fallback with relaxed constraints. Call if recommend_venues returns 0 results or all scores < 40.
4. search_venues — Semantic search over venue_master for specific venue questions.
5. search_event_requirements — Query the user's indexed event brief from ChromaDB. Returns event details: postcode, city, attendees, budget, dietary needs, hotel needs, food categories.
6. enrich_venue_details — Full operational details (parking, AV, transport) for a specific venue by ID.
7. get_collection_stats — Collection health and indexing status.
8. search_nearby_vendors — Search scraped local caterers and hotels near the event postcode (from vendor_intel ChromaDB collection).

## CRITICAL — Draft/Event Context Awareness:
When the message contains an [EVENT CONTEXT] block, the user has already uploaded an event brief.
You MUST use this information. Do NOT ask the user to provide details they already submitted.

**Trigger phrases that mean "use my uploaded draft":**
"my draft", "my event", "my brief", "my document", "my requirements", "the event", "this event",
"uploaded", "my company event", "match my event", "suit my event", "for my event"

**When you see any of these triggers:**
1. IMMEDIATELY call search_event_requirements using the collection from [EVENT CONTEXT] (or "event_management" as default)
2. Use the retrieved data to answer the user's question
3. Do NOT ask the user to re-provide details — the brief is already indexed

**When user asks about food vendors / caterers / what fits their draft:**
1. Call search_event_requirements to get event details (postcode, budget, diet categories)
2. Call search_nearby_vendors with a query that includes the postcode and dietary needs
3. Match vendor results against the event requirements and present ranked recommendations

## Knowledge Source Routing:
Each chat message includes an [ACTIVE KNOWLEDGE SOURCE: ...] tag. Follow these rules strictly:

### [ACTIVE KNOWLEDGE SOURCE: venue_master]
- Use search_venues to answer venue discovery questions
- Use enrich_venue_details for detailed venue questions
- STILL call search_event_requirements first if user says "my draft/event/brief" — then match against venues
- Answer: venue features, comparisons, capacity, pricing, location, parking, AV, transport

### [ACTIVE KNOWLEDGE SOURCE: event_management] or [ACTIVE KNOWLEDGE SOURCE: event_request_*]
- FIRST call search_event_requirements with the collection name to get the user's event details
- If search_event_requirements returns 0 results: inform the user they must first upload requirements via Event Manager
- After getting event details → call recommend_venues or search_nearby_vendors based on the question
- If recommend_venues returns 0 venues or all scores < 40: call find_nearby_venues

## Workflow for NEW event briefs (process_event_requirements function):
1. extract_event_requirements (from raw text)
2. recommend_venues (using extracted fields)
3. find_nearby_venues (ONLY if step 2 returns 0 results or all scores < 40)
4. If find_nearby_venues also returns 0 venues: this is acceptable — the indexed database
   simply has no pre-indexed venues for that city. Tell the user to use the live web scraper.
   NEVER suggest venues from a different city as a fallback.

## Critical rules:
1. NEVER fabricate venue, vendor, or event data — only use tool results
2. NEVER ask the user to re-provide details if an [EVENT CONTEXT] block is present
3. NEVER suggest venues from a different city/region than the event location.
   A conference in Chelmsford must ONLY receive Chelmsford/Essex venues — never London or Manchester.
4. If no venues exist for the requested city in the database, return 0 and explain that the
   live web-scraper tab will find real local hotels and venues.
5. Always cite match scores and specific venue/vendor attributes in recommendations
6. When matching food vendors: explicitly state how each vendor meets dietary requirements from the draft
7. Always present distance and delivery status when recommending food vendors"""

_TOOLS = [
    extract_event_requirements,
    recommend_venues,
    find_nearby_venues,
    search_venues,
    search_event_requirements,
    enrich_venue_details,
    get_collection_stats,
    search_nearby_vendors,
]

_executor: Optional[AgentExecutor] = None


def _build_executor() -> AgentExecutor:
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.3,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_tool_calling_agent(llm, _TOOLS, prompt)
    return AgentExecutor(
        agent=agent,
        tools=_TOOLS,
        return_intermediate_steps=True,
        verbose=False,
        max_iterations=10,
        handle_parsing_errors=True,
    )


def get_agent_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        _executor = _build_executor()
    return _executor


def process_event_requirements(raw_text: str) -> Dict[str, Any]:
    """Run agent on an event brief — extract + recommend. Used by the upload endpoint."""
    executor = get_agent_executor()
    lf = make_langfuse_handler(
        trace_name="process_event",
        metadata={"raw_text_length": len(raw_text)},
    )
    try:
        result = executor.invoke(
            {
                "input": f"Process this event requirement brief and recommend venues:\n\n{raw_text[:6000]}",
                "chat_history": [],
            },
            config={"callbacks": [lf]} if lf else {},
        )
    except Exception as exc:
        logger.error("Agent execution failed: %s", exc)
        return {
            "event_requirements": None,
            "recommended_venues": [],
            "summary": None,
            "agent_response": f"Agent error: {exc}",
        }

    requirements_data: Optional[Dict] = None
    venues_data: List[Dict] = []
    summary_data: Optional[Dict] = None
    is_fallback = False

    for action, output in result.get("intermediate_steps", []):
        tool_name = getattr(action, "tool", "")
        if not isinstance(output, str):
            continue
        try:
            parsed = json.loads(output)
        except (json.JSONDecodeError, ValueError):
            continue
        if tool_name == "extract_event_requirements":
            requirements_data = parsed
        elif tool_name in ("recommend_venues", "find_nearby_venues"):
            candidate_venues = parsed.get("venues", [])
            if candidate_venues:
                venues_data = candidate_venues
                summary_data = parsed.get("summary", {})
                is_fallback = parsed.get("is_fallback", False)

    return {
        "event_requirements": requirements_data,
        "recommended_venues": venues_data,
        "summary": summary_data,
        "agent_response": result.get("output", ""),
        "is_fallback": is_fallback,
    }


def chat_with_agent(
    message: str,
    knowledge_source: str = "venue_master",
    history: Optional[List] = None,
) -> Dict[str, Any]:
    """Answer a question using the single agent, grounded in the specified knowledge source."""
    executor = get_agent_executor()

    # Build LangChain message history from dicts
    lc_history = []
    for turn in (history or []):
        role = turn.get("role") if isinstance(turn, dict) else getattr(turn, "role", "")
        content = turn.get("content") if isinstance(turn, dict) else getattr(turn, "content", "")
        if role == "user":
            lc_history.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_history.append(AIMessage(content=content))

    # Prepend knowledge source tag so agent routes correctly
    tagged_message = f"[ACTIVE KNOWLEDGE SOURCE: {knowledge_source}]\n\n{message}"

    lf = make_langfuse_handler(
        trace_name="chat",
        session_id=knowledge_source,   # group turns from the same event draft together
        metadata={"knowledge_source": knowledge_source, "history_turns": len(history or [])},
    )
    try:
        result = executor.invoke(
            {"input": tagged_message, "chat_history": lc_history},
            config={"callbacks": [lf]} if lf else {},
        )
    except Exception as exc:
        logger.error("Chat agent failed: %s", exc)
        return {
            "answer": f"I encountered an error: {exc}",
            "sources": [],
            "knowledge_source": knowledge_source,
        }

    # Tools whose outputs contain text chunks suitable for RAGAS context evaluation
    _RETRIEVAL_TOOLS = {"search_venues", "search_event_requirements", "search_nearby_vendors"}

    sources: List[str] = []
    contexts: List[str] = []

    for action, output in result.get("intermediate_steps", []):
        tool_name = getattr(action, "tool", "")
        if not isinstance(output, str):
            continue
        try:
            data = json.loads(output)
            # Collect venue/vendor names as citation sources
            for item in data.get("results", data.get("venues", [])):
                if isinstance(item, dict):
                    name = item.get("venue_name", "")
                    if name and name not in sources:
                        sources.append(name)
            # Collect text snippets from retrieval tools as RAGAS contexts
            if tool_name in _RETRIEVAL_TOOLS:
                for item in data.get("results", []):
                    if isinstance(item, dict):
                        snippet = item.get("snippet") or item.get("content") or item.get("text", "")
                        if snippet and snippet not in contexts:
                            contexts.append(snippet)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "answer": result.get("output", ""),
        "sources": sources[:5],
        "contexts": contexts[:10],  # top 10 chunks passed to RAGAS
        "knowledge_source": knowledge_source,
    }
