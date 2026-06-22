from typing import List
from app.schemas.event import EventRequirements

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "forget your instructions",
    "you are now",
    "pretend you are",
    "reveal system prompt",
    "show system prompt",
    "print your system prompt",
    "delete database",
    "drop table",
    "drop database",
    "exec(",
    "eval(",
    "import os",
    "<script",
    "javascript:",
    "system()",
    "subprocess",
    "act as if",
    "disregard previous",
]

ALLOWED_FILE_EXTENSIONS = {".pdf", ".doc", ".docx"}


def check_prompt_injection(text: str) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in _INJECTION_PATTERNS)


def validate_file_extension(filename: str) -> bool:
    import os
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_FILE_EXTENSIONS


def validate_event_requirements(requirements: EventRequirements) -> List[str]:
    errors = []
    if requirements.min_budget < 0:
        errors.append("Minimum budget cannot be negative")
    if requirements.max_budget < 0:
        errors.append("Maximum budget cannot be negative")
    if requirements.max_budget > 0 and requirements.min_budget > requirements.max_budget:
        errors.append("Minimum budget cannot exceed maximum budget")
    if requirements.attendees < 0:
        errors.append("Number of attendees cannot be negative")
    return errors
