from typing import List, Dict, Optional
from app.core.config import settings


def get_llm():
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
        )
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
    )


def build_system_prompt(module: str) -> str:
    base = (
        "You are an AI assistant for the Family Finance & Company Event Planning platform. "
        "Answer clearly and concisely. If you have retrieved context, use it to answer precisely. "
        "Always provide actionable insights where possible."
    )
    extra = {
        "family": " You specialise in household budgeting, expense tracking, savings, and grocery vendor comparisons in the UK.",
        "company": " You specialise in company event planning, budget allocation, vendor selection, and cost optimisation.",
        "vendor": " You specialise in vendor pricing, comparisons across UK supermarkets and catering companies.",
    }
    return base + extra.get(module, "")


def chat_with_llm(
    messages: List[Dict[str, str]],
    module: str = "family",
    context: Optional[str] = None,
) -> Dict:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    import time

    llm = get_llm()

    lc_messages = [SystemMessage(content=build_system_prompt(module))]

    if context:
        lc_messages.append(SystemMessage(content=f"Retrieved context:\n{context}"))

    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))

    start = time.time()
    response = llm.invoke(lc_messages)
    latency_ms = round((time.time() - start) * 1000, 1)

    token_usage = getattr(response, "usage_metadata", None)
    tokens_used = token_usage.get("total_tokens") if isinstance(token_usage, dict) else None

    return {
        "content": response.content,
        "model_used": settings.openai_model if settings.llm_provider != "anthropic" else settings.anthropic_model,
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
    }
