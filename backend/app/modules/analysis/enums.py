"""Analysis vocabulary. Stored as text, so the values are the contract."""

from __future__ import annotations

from enum import StrEnum


class Verdict(StrEnum):
    """A requirement is met, partly met, or not met. Never a free-form score."""

    STRONG = "strong"
    PARTIAL = "partial"
    GAP = "gap"


class Importance(StrEnum):
    """Knockout gaps are the only ones that can cap the fit label."""

    KNOCKOUT = "knockout"
    WEIGHT = "weight"
    NICE = "nice"


class RequirementCategory(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    LANGUAGE = "language"
    TOOL = "tool"
    DOMAIN = "domain"
    LOGISTICS = "logistics"
    OTHER = "other"


class ExtractionStatus(StrEnum):
    OK = "ok"
    JD_NOT_FOUND = "jd_not_found"
    JD_MULTIPLE_JOBS = "jd_multiple_jobs"
    LLM_INVALID = "llm_invalid"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SuggestionType(StrEnum):
    """`GAP_NOTE` carries no rewrite text: it names a gap the CV cannot close."""

    REWORD = "reword"
    REORDER = "reorder"
    EMPHASIZE = "emphasize"
    ADD_KEYWORD = "add_keyword"
    GAP_NOTE = "gap_note"


class SuggestionScope(StrEnum):
    """Per D9: an edit that improves the master CV, or one aimed at this post."""

    GENERAL = "general"
    JOB_SPECIFIC = "job_specific"


class SuggestionTarget(StrEnum):
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    SKILLS = "skills"
    PROJECTS = "projects"
    EDUCATION = "education"
    CERTIFICATIONS = "certifications"
    OTHER = "other"


class GuardStatus(StrEnum):
    """`pass`, or `rejected_<rule>` naming the single rule that fired (§8.8)."""

    PASS = "pass"  # noqa: S105 - a guard state, not a password


class SuggestionDecision(StrEnum):
    UNDECIDED = "undecided"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TaskKind(StrEnum):
    ANALYZE = "analyze"
    STRUCTURE_JD = "structure_jd"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Step(StrEnum):
    """Pipeline steps, in the order code runs them (S0..S9)."""

    S0_PREFLIGHT = "s0_preflight"
    S1_EXTRACT = "s1_extract"
    S2_MATCH = "s2_match"
    S3_GROUND = "s3_ground"
    S4_VOTE = "s4_vote"
    S5_SUGGEST = "s5_suggest"
    S6_FABRICATION_GUARD = "s6_fabrication_guard"
    S7_COVER_NOTE = "s7_cover_note"
    S8_COVER_NOTE_GUARD = "s8_cover_note_guard"
    S9_PERSIST = "s9_persist"


STEPS: tuple[str, ...] = tuple(step.value for step in Step)


class LlmOutcome(StrEnum):
    OK = "ok"
    INVALID = "invalid"
    ERROR = "error"
    TIMEOUT = "timeout"
