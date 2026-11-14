from __future__ import annotations

from enum import StrEnum


class JobSource(StrEnum):
    GMAIL_ALERT = "gmail_alert"
    MANUAL = "manual"


class JobStatus(StrEnum):
    NEW = "new"
    SHORTLISTED = "shortlisted"
    DISMISSED = "dismissed"
    ANALYZED = "analyzed"
    APPLIED = "applied"


class JobOutcome(StrEnum):
    NONE = "none"
    NO_RESPONSE = "no_response"
    REJECTED = "rejected"
    INTERVIEW = "interview"
    OFFER = "offer"


class SnapshotSourceKind(StrEnum):
    PAGE_PASTE = "page_paste"
    TEXT_PASTE = "text_paste"
    URL_FETCH = "url_fetch"


WORK_MODES: tuple[str, ...] = ("remote", "hybrid", "onsite")
