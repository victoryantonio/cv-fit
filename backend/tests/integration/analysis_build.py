"""Scripted world shared by the analysis integration tests.

The LLM and the file parser are faked; everything else is the real container.
Two modules use this, so the data lives here rather than in a test module.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.container import Container
from app.modules.cvs.parser import ParsedCv
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK
from tests.fixtures.documents import build_docx
from tests.fixtures.jd_texts import CLEAN_PAGE

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
REQUIREMENT_COUNT = 5
MATCH_RUNS = 1

CV_ONE = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
    "Reviewed merge requests and paired with two junior engineers each week.\n"
)

CV_TWO = CV_ONE + "Migrated the settlement worker to ECS in 2023 with a zero-downtime cutover.\n"

QUOTE_PYTHON = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)
QUOTE_SQL = "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation."
QUOTE_MENTOR = "Reviewed merge requests and paired with two junior engineers each week."
QUOTE_PROFILE = "Backend engineer with six years building payment and ledger services in Python."

STRONG_PYTHON: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_PYTHON,
    "rationale": "Names the work, the language and the outcome.",
    "missing": [],
}
STRONG_SQL: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_SQL,
    "rationale": "Names the database and the query work.",
    "missing": [],
}
GAP_AWS: dict[str, Any] = {
    "verdict": "gap",
    "evidence_quote": None,
    "rationale": "The CV never mentions a cloud provider.",
    "missing": ["AWS", "ECS", "Kubernetes"],
}
PARTIAL_MENTOR: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": QUOTE_MENTOR,
    "rationale": "Shows review and pairing, not formal mentoring of mid-level engineers.",
    "missing": ["mid-level engineers"],
}
PARTIAL_ENGLISH: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": QUOTE_PROFILE,
    "rationale": "Shows written work, not a language test.",
    "missing": ["written English"],
}

UNGROUNDED: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": "Six years of Kubernetes in production",
    "rationale": "Not in the CV, so the grounding check must discard it.",
    "missing": [],
}

#: Suggestion tests live in their own module; here S5 only has to answer.
SUGGEST_NONE: dict[str, Any] = {"suggestions": []}


class NamedParser:
    """Two CVs must differ in text; the uploaded bytes may be identical."""

    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts
        self.calls: list[str] = []

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        self.calls.append(file_name)
        text = self._texts[Path(file_name).stem]
        return ParsedCv(text=text, sections={"other": text}, warnings=[], kind="docx")


def per_run_script(executions: int = 2) -> list[dict[str, Any]]:
    """One analysis = three identical runs per requirement, then S5, then S7.

    The default covers two analyses: the tests that compare two CV versions would
    otherwise exhaust the script and fail with a fake, not a real, error.
    """
    ordered = [STRONG_PYTHON, STRONG_SQL, GAP_AWS, PARTIAL_MENTOR, PARTIAL_ENGLISH]
    run: list[dict[str, Any]] = [payload for payload in ordered for _ in range(MATCH_RUNS)]
    run.append(SUGGEST_NONE)
    run.append(COVER_OK)
    return [payload for _ in range(executions) for payload in run]


Build = Callable[[list[object] | None], tuple[Container, FakeLLMClient]]


def make_job(container: Container) -> tuple[str, dict[str, str]]:
    job = container.jobs.create(title="Senior Backend Engineer")
    snapshot = container.jobs.add_snapshot(job["id"], raw_text=CLEAN_PAGE, source_kind="page_paste")
    return str(job["id"]), snapshot


def make_version(container: Container, label: str) -> str:
    cv = container.cvs.create(label=f"CV {label}")
    stored = container.cvs.add_version(cv["id"], file_name=f"{label}.docx", data=build_docx())
    return str(stored["id"])
