"""
Extraction Agent — uses LangChain structured output to pull event details from raw document text.
This is a single-purpose agent: given text, return a typed EventExtractionOutput.
"""
import logging
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are an expert at reading event planning documents and extracting structured information.
Extract exactly what is in the document. If a field is not found, return null.
For budget, return only the numeric value in GBP (strip currency symbols).
For food_required: true if the document mentions food, catering, meals, refreshments, or dining.
For hosting_required: true if the document mentions hotel, accommodation, overnight, or venue stay.
Return null for any field that cannot be determined from the document.""",
    ),
    ("human", "Extract event details from this document text:\n\n{text}"),
])


class EventExtractionOutput(BaseModel):
    event_name: str = Field(description="Name of the event")
    city: Optional[str] = Field(None, description="City where the event takes place")
    event_date: Optional[str] = Field(None, description="Date of the event")
    event_time: Optional[str] = Field(None, description="Start time (HH:MM)")
    attendee_count: Optional[int] = Field(None, description="Number of attendees")
    number_of_days: Optional[int] = Field(None, description="Duration in days")
    food_required: Optional[bool] = Field(None, description="Whether catering/food is required")
    hosting_required: Optional[bool] = Field(None, description="Whether hotel/accommodation is required")
    budget: Optional[float] = Field(None, description="Total budget in GBP as numeric value")


def run_extraction(text: str) -> dict:
    """
    Run the extraction agent on the provided document text.
    Returns a dict matching EventExtractionOutput fields.
    Falls back to a minimal dict on failure.
    """
    from app.modules.chat.llm import get_llm

    # Truncate to avoid excessive token usage
    truncated = text[:6000]

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(EventExtractionOutput)
        chain = EXTRACTION_PROMPT | structured_llm
        result: EventExtractionOutput = chain.invoke({"text": truncated})
        extracted = result.model_dump()
        logger.info("Extraction agent succeeded: event_name=%s", extracted.get("event_name"))
        return extracted
    except Exception as e:
        logger.error("Extraction agent failed: %s", e)
        # Return minimal fallback so the event is still stored
        return {"event_name": "Extracted Event", "extraction_error": str(e)}
