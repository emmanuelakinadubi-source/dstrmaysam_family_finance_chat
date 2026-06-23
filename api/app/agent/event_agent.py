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
from app.agent.tools.venue_retrieval_tool import search_venues
from app.core.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert Corporate Event Planning AI Consultant operating as a unified Event Manager platform.

## Tools:
1. extract_event_requirements — Parse raw text → structured event fields (call FIRST for event briefs)
2. recommend_venues — Find and rank venues (40/20/15/10/10/5 scoring). Call after extraction.
3. find_nearby_venues — Fallback with relaxed constraints. Call if recommend_venues returns 0 results or all scores < 40.
4. search_venues — Semantic search over venue_master for specific venue questions.
5. search_event_requirements — Query indexed event requirements from event_management or event_request_* collection.
6. enrich_venue_details — Full operational details (parking, AV, transport) for a specific venue by ID.
7. get_collection_stats — Collection health and indexing status.

## Knowledge Source Routing:
Each chat message includes an [ACTIVE KNOWLEDGE SOURCE: ...] tag. Follow these rules strictly:

### [ACTIVE KNOWLEDGE SOURCE: venue_master]
- Use search_venues to answer venue discovery questions
- Use enrich_venue_details for detailed operational questions about a specific venue
- Answer: venue features, comparisons, capacity, pricing, location, parking, AV, transport
- Do NOT call search_event_requirements

### [ACTIVE KNOWLEDGE SOURCE: event_management] or [ACTIVE KNOWLEDGE SOURCE: event_request_*]
- FIRST call search_event_requirements with the collection name to get the user's event details
- If search_event_requirements returns 0 results: inform the user they must first upload requirements via Event Manager
- After getting event details, if the user asks for venue recommendations: call recommend_venues with the extracted event fields
- If recommend_venues returns 0 venues or all scores < 40: call find_nearby_venues
- Use search_venues for specific venue feature questions
- Answer: event requirements Q&A, venue matching, budget analysis, suitability scores

## Workflow for event briefs (process_event_requirements function):
1. extract_event_requirements (from raw text)
2. recommend_venues (using extracted fields)
3. find_nearby_venues (ONLY if step 2 returns 0 results or all scores < 40)

## Critical rules:
1. NEVER fabricate venue or event data — only use tool results
2. NEVER return 0 venues without first calling find_nearby_venues
3. Always cite match scores and specific venue attributes in recommendations
4. For event_management queries: always call search_event_requirements first, then reason over results
5. Include clear reasoning/explanation for every venue recommendation"""

_TOOLS = [
    extract_event_requirements,
    recommend_venues,
    find_nearby_venues,
    search_venues,
    search_event_requirements,
    enrich_venue_details,
    get_collection_stats,
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
    try:
        result = executor.invoke({
            "input": f"Process this event requirement brief and recommend venues:\n\n{raw_text[:6000]}",
            "chat_history": [],
        })
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

    try:
        result = executor.invoke({"input": tagged_message, "chat_history": lc_history})
    except Exception as exc:
        logger.error("Chat agent failed: %s", exc)
        return {
            "answer": f"I encountered an error: {exc}",
            "sources": [],
            "knowledge_source": knowledge_source,
        }

    sources = []
    for action, output in result.get("intermediate_steps", []):
        if not isinstance(output, str):
            continue
        try:
            data = json.loads(output)
            for item in data.get("results", data.get("venues", [])):
                if isinstance(item, dict):
                    name = item.get("venue_name", "")
                    if name and name not in sources:
                        sources.append(name)
        except (json.JSONDecodeError, TypeError):
            pass

    return {
        "answer": result.get("output", ""),
        "sources": sources[:5],
        "knowledge_source": knowledge_source,
    }
