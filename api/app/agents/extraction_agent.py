"""Agent 1 – Requirement Extraction Agent.

Parses raw text (from PDF, DOCX, or direct input) and returns structured
EventRequirements using the LLM with a zero-temperature structured JSON response.
"""
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from app.core.config import settings
from app.schemas.event import EventRequirements

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an Event Planning AI Assistant.

Extract event requirements from the provided text and return ONLY a valid JSON object — no markdown, no explanation.

Return exactly this schema:
{
    "event_date": "",
    "event_time": "",
    "city": "",
    "min_budget": 0,
    "max_budget": 0,
    "attendees": 0,
    "additional_requirements": []
}

Field rules:
- event_date: ISO format YYYY-MM-DD, or empty string
- event_time: HH:MM 24h format, or empty string
- city: city/town name, or empty string
- min_budget: numeric GBP value, 0 if not mentioned
- max_budget: numeric GBP value, 0 if not mentioned
- attendees: integer headcount, 0 if not mentioned
- additional_requirements: list of strings for any special needs

Return ONLY the JSON object."""


def extract_requirements(text: str) -> EventRequirements:
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Extract requirements from:\n\n{text[:4000]}"),
    ]
    try:
        response = _get_llm().invoke(messages)
        raw = _clean_json(response.content)
        data = json.loads(raw)
        return EventRequirements(**data)
    except Exception as exc:
        logger.error("Extraction failed: %s", exc)
        return EventRequirements()


def _clean_json(text: str) -> str:
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # Grab the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def _get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0,
    )
