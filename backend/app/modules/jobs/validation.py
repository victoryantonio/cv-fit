"""Input checks for job intake: lengths, required fields, enum choices.

Pure functions that raise the same VALIDATION_ERROR shape the API reports, kept
apart from the service so the service reads as the story of a job, not of a field.
"""

from __future__ import annotations

from typing import Final

from app.modules.jobs.enums import JobStatus
from app.modules.jobs.jd_input import MAX_JD_CHARS, MIN_JD_CHARS
from app.modules.jobs.prefilter import PrefilterCriteria
from app.shared.errors import AppError

MAX_TITLE_CHARS: Final = 200
MAX_COMPANY_CHARS: Final = 200
MAX_LOCATION_CHARS: Final = 200
MAX_URL_CHARS: Final = 1000

# AFD §5. `new` may go straight to `analyzed` because the pipeline sets it (F06).
ALLOWED_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    JobStatus.NEW: frozenset({JobStatus.SHORTLISTED, JobStatus.DISMISSED, JobStatus.ANALYZED}),
    JobStatus.SHORTLISTED: frozenset({JobStatus.ANALYZED, JobStatus.DISMISSED}),
    JobStatus.ANALYZED: frozenset({JobStatus.APPLIED}),
    JobStatus.DISMISSED: frozenset({JobStatus.NEW}),
    JobStatus.APPLIED: frozenset(),
}


def clean(value: str | None, *, field: str, max_chars: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_chars:
        raise AppError(
            "VALIDATION_ERROR",
            f"{field} must be at most {max_chars} characters.",
            {"field": field, "max_chars": max_chars},
        )
    return cleaned


def required_title(title: str) -> str:
    cleaned = title.strip()
    if not 1 <= len(cleaned) <= MAX_TITLE_CHARS:
        raise AppError(
            "VALIDATION_ERROR",
            f"A title of 1 to {MAX_TITLE_CHARS} characters is required.",
            {"field": "title"},
        )
    return cleaned


def check_choice(value: str, allowed: tuple[str, ...], *, field: str) -> str:
    if value not in allowed:
        raise AppError(
            "VALIDATION_ERROR",
            f"{field} must be one of: {', '.join(allowed)}.",
            {"field": field, "allowed": list(allowed)},
        )
    return value


def check_length(raw_text: str) -> None:
    length = len(raw_text)
    if length < MIN_JD_CHARS:
        raise AppError(
            "VALIDATION_ERROR",
            f"The text is under {MIN_JD_CHARS} characters. Paste the full job page.",
            {
                "field": "raw_text",
                "reason": "too_short",
                "chars": length,
                "min_chars": MIN_JD_CHARS,
            },
        )
    if length > MAX_JD_CHARS:
        raise AppError(
            "VALIDATION_ERROR",
            f"The text is over {MAX_JD_CHARS} characters. Paste one job only.",
            {"field": "raw_text", "reason": "too_long", "chars": length, "max_chars": MAX_JD_CHARS},
        )


def no_criteria() -> PrefilterCriteria:
    """Unconfigured means nothing is pre-filtered, not that everything is kept."""
    return PrefilterCriteria()




