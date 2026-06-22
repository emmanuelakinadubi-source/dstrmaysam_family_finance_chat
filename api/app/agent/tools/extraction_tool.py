import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

_EXTRACTION_SYSTEM_PROMPT = """You are an Event Planning AI Assistant.

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


class ExtractionInput(BaseModel):
    raw_text: str = Field(description="Raw event requirement text from PDF, DOCX, or direct user input")


def _extract_fn(raw_text: str) -> str:
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0,
    )
    messages = [
        SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=f"Extract requirements from:\n\n{raw_text[:4000]}"),
    ]
    try:
        response = llm.invoke(messages)
        text = response.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return json.dumps(data)
    except Exception as exc:
        logger.error("Extraction failed: %s", exc)
    return json.dumps({
        "event_date": "", "event_time": "", "city": "",
        "min_budget": 0, "max_budget": 0, "attendees": 0,
        "additional_requirements": [],
    })


extract_event_requirements = StructuredTool.from_function(
    func=_extract_fn,
    name="extract_event_requirements",
    description=(
        "Parse raw event requirement text (from PDF, DOCX, or typed input) into structured fields. "
        "Returns JSON with: event_date, event_time, city, min_budget, max_budget, attendees, additional_requirements. "
        "Always call this FIRST when processing an event brief."
    ),
    args_schema=ExtractionInput,
)
