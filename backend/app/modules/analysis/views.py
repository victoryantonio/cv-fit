"""The two shapes the pipeline passes around: a requirement as read, and a JD.

Both are frozen values. Nothing here touches a model or a session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

from app.modules.analysis.enums import Importance
from app.modules.analysis.schemas import JdStructure
from app.shared.text import sha256_hex

# Extraction order: the strongest signal first, so a 40-item cut keeps what matters.
IMPORTANCE_ORDER: Final[dict[str, int]] = {
    Importance.KNOCKOUT: 0,
    Importance.WEIGHT: 1,
    Importance.NICE: 2,
}


@dataclass(frozen=True, slots=True)
class RequirementView:
    id: str
    position: int
    text: str
    category: str
    importance: str
    keywords: list[str]
    jd_quote: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "position": self.position,
            "text": self.text,
            "category": self.category,
            "importance": self.importance,
            "keywords": list(self.keywords),
            "jd_quote": self.jd_quote,
        }


@dataclass(frozen=True, slots=True)
class StructuredJd:
    extraction_id: str
    snapshot_id: str
    status: str
    structure: JdStructure | None
    requirements: list[RequirementView] = field(default_factory=list)
    dropped_quotes: int = 0
    duplicates: int = 0
    warnings: list[str] = field(default_factory=list)
    cache_hit: bool = False
    tokens_in: int = 0
    tokens_out: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "extraction_id": self.extraction_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "requirements": [item.as_dict() for item in self.requirements],
            "requirement_count": len(self.requirements),
            "dropped_quotes": self.dropped_quotes,
            "duplicates": self.duplicates,
            "warnings": list(self.warnings),
            "cache_hit": self.cache_hit,
        }
        if self.structure is not None:
            payload["job"] = {
                "title": self.structure.title,
                "company": self.structure.company,
                "location": self.structure.location,
                "work_mode": self.structure.work_mode,
                "seniority": self.structure.seniority,
                "languages": list(self.structure.languages),
                "salary_text": self.structure.salary_text,
                "work_authorization_text": self.structure.work_authorization_text,
                "is_job_post": self.structure.is_job_post,
                "job_count": self.structure.job_count,
            }
        return payload


def extraction_key(*, text_sha256: str, prompt_bundle: str, model: str) -> str:
    """One key per (text, prompt set, model). A settings change invalidates it."""
    return sha256_hex(f"{text_sha256}|{prompt_bundle}|{model}")
