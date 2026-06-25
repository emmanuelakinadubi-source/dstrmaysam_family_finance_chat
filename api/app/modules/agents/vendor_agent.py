"""
Vendor Agent — a LangChain tool-calling agent that reasons about vendor selection
given event requirements. Uses DB query tools to look up vendors and generate
a natural-language explanation of recommendations.
"""
import logging
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

logger = logging.getLogger(__name__)

VENDOR_AGENT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a company event procurement specialist. Your job is to recommend vendors
for company events. You have access to tools to query the vendor database.

When recommending vendors:
1. Use the query_vendors tool to fetch relevant vendors
2. Calculate costs based on attendee count and duration
3. Compare against the budget
4. Explain WHY each vendor is recommended
5. Clearly state budget remaining or shortfall

Always be concise and actionable.""",
    ),
    MessagesPlaceholder("chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])


@tool
def query_vendors(city: str = "", vendor_type: str = "") -> str:
    """Query the vendor database. Provide city and/or vendor_type to filter results.
    vendor_type options: Catering, Hotel, Conference"""
    try:
        from app.core.database import SessionLocal
        from app.models.vendor import Vendor

        db = SessionLocal()
        q = db.query(Vendor).filter(Vendor.is_active.is_(True))
        if city:
            q = q.filter(Vendor.city.ilike(f"%{city}%"))
        if vendor_type:
            q = q.filter(Vendor.vendor_type.ilike(f"%{vendor_type}%"))
        vendors = q.all()
        db.close()

        if not vendors:
            return "No vendors found matching the criteria."

        lines = ["Available vendors:"]
        for v in vendors:
            lines.append(
                f"- {v.vendor_name} ({v.vendor_type}) in {v.city}: £{v.price_per_person}/person"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Database error: {e}"


@tool
def calculate_event_cost(price_per_person: float, attendee_count: int, days: int = 1) -> str:
    """Calculate total event cost for a vendor. Use days=1 for catering (per event),
    higher for hotels (per night)."""
    total = price_per_person * attendee_count * days
    return f"Total cost: £{total:,.2f} (£{price_per_person}/person × {attendee_count} people × {days} days)"


def get_vendor_agent() -> AgentExecutor:
    from app.modules.chat.llm import get_llm
    llm = get_llm()
    tools = [query_vendors, calculate_event_cost]
    agent = create_openai_tools_agent(llm, tools, VENDOR_AGENT_PROMPT)
    return AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=5)


def run_vendor_reasoning(
    city: str,
    attendee_count: int,
    budget: float,
    number_of_days: int = 1,
    food_required: bool = True,
    hosting_required: bool = True,
) -> str:
    """
    Run the vendor agent and return a natural-language recommendation summary.
    Falls back to simple text if agent fails.
    """
    prompt = (
        f"We need vendor recommendations for a company event:\n"
        f"- City: {city}\n"
        f"- Attendees: {attendee_count}\n"
        f"- Duration: {number_of_days} day(s)\n"
        f"- Total budget: £{budget:,.2f}\n"
        f"- Food/catering required: {food_required}\n"
        f"- Hotel/accommodation required: {hosting_required}\n\n"
        "Please query available vendors and recommend the best options. "
        "Calculate costs and compare against the budget."
    )
    try:
        executor = get_vendor_agent()
        result = executor.invoke({"input": prompt})
        return result.get("output", "No recommendation generated.")
    except Exception as e:
        logger.warning("Vendor agent failed, using fallback: %s", e)
        return f"Vendor agent unavailable: {e}"
