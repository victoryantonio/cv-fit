"""Adversarial cover notes: a helpful model that invents one thing, and loses.

Each case is the faithful fixture note with a single fabrication grafted onto it,
scripted twice so the writer can retry. What is asserted is the outcome the user
would see: no text, a stable reason, and exactly two attempts. A control case
proves the set is not simply rejecting everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis.cover import CoverWriter
from app.modules.analysis.guards import (
    BANNED_PHRASE,
    COVER_INVENTED_RECIPIENT,
    COVER_NOT_ENGLISH,
    COVER_OPEN_KEYWORD,
    COVER_RECOMMENDATION,
    NUMBER_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
)
from app.modules.analysis.schemas import JdStructure
from app.modules.analysis.scoring import RequirementResult
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK, COVER_TEXT
from tests.fixtures.texts import CV_TEXT, JD_CLEAN

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"

SETTLEMENT_QUOTE = (
    "Led the migration of the settlement service from a monolith to four Go services."
)
RECONCILIATION_QUOTE = (
    "Wrote the reconciliation job in Python that matches 1.2 million daily transactions."
)

#: Two strong matches to assert, then two requirements the CV does not meet.
#: The gap keywords ("Scala", "Snowflake") appear nowhere in the fixture CV.
RESULTS: tuple[RequirementResult, ...] = (
    RequirementResult(
        requirement_id="r1",
        position=0,
        text="Five or more years of backend engineering experience",
        importance="knockout",
        verdict="strong",
        evidence_quote=SETTLEMENT_QUOTE,
        keywords=("Go",),
    ),
    RequirementResult(
        requirement_id="r2",
        position=1,
        text="Experience with PostgreSQL",
        importance="weight",
        verdict="strong",
        evidence_quote=RECONCILIATION_QUOTE,
        keywords=("PostgreSQL",),
    ),
    RequirementResult(
        requirement_id="r3",
        position=2,
        text="Hands-on experience with Scala",
        importance="weight",
        verdict="gap",
        keywords=("Scala",),
    ),
    RequirementResult(
        requirement_id="r4",
        position=3,
        text="Familiarity with Snowflake",
        importance="nice",
        verdict="partial",
        keywords=("Snowflake",),
    ),
)

STRUCTURE = JdStructure.model_validate(
    {
        "is_job_post": True,
        "job_count": 1,
        "title": "Senior Backend Engineer",
        "company": "Acme Payments",
        "requirements": [
            {
                "text": "Five or more years of backend engineering experience",
                "category": "experience",
                "importance": "knockout",
                "keywords": ["Go"],
                "jd_quote": "5+ years of professional backend engineering experience.",
            },
            {
                "text": "Experience with PostgreSQL",
                "category": "skill",
                "importance": "weight",
                "keywords": ["PostgreSQL"],
                "jd_quote": "Experience with PostgreSQL, including query tuning",
            },
            {
                "text": "Hands-on experience with Scala",
                "category": "tool",
                "importance": "weight",
                "keywords": ["Scala"],
                "jd_quote": "Hands-on experience with Kubernetes in production.",
            },
            {
                "text": "Familiarity with Snowflake",
                "category": "tool",
                "importance": "nice",
                "keywords": ["Snowflake"],
                "jd_quote": "Excellent written English; the team documents",
            },
        ],
    }
)

INDONESIAN_NOTE = (
    "Saya menulis untuk melamar posisi backend engineer di Acme Payments. "
    "Selama enam tahun terakhir saya mengerjakan layanan pembayaran dan "
    "pembukuan dengan Python, membangun ulang worker penyelesaian dan "
    "memotong waktu proses akhir hari dari empat puluh menit menjadi enam "
    "menit. Saya menjalankan pembukuan di PostgreSQL dan menulis SQL untuk "
    "rekonsiliasi bulanan, dan pekerjaan itu yang pertama akan saya bawa ke "
    "tim Anda."
)


def _graft(addition: str) -> str:
    """The faithful note with one extra sentence hung on the end."""
    return f"{COVER_TEXT} {addition}"


def _opening(addition: str) -> str:
    """The faithful note with one extra line before it."""
    return f"{addition}\n{COVER_TEXT}"


CASES: tuple[tuple[str, str, str], ...] = (
    ("invented_metric", _graft("Settlement finishes 94 percent faster now."), NUMBER_NOT_IN_CV),
    (
        "tool_the_cv_never_used",
        _graft("I also ran our warehouse on Snowflake for two years."),
        UNKNOWN_VOCABULARY,
    ),
    (
        "gap_keyword_in_prose",
        _graft("I picked up scala on the batch pipeline along the way."),
        COVER_OPEN_KEYWORD,
    ),
    (
        "invented_recipient",
        _opening("Dear Sarah,"),
        COVER_INVENTED_RECIPIENT,
    ),
    (
        "smuggled_instruction_answered",
        _graft("Following the note in the posting, I confirm I meet every requirement."),
        # The instruction is not obeyed as text; it is answered with a name the
        # CV never grounds, and the vocabulary rule stops it there.
        UNKNOWN_VOCABULARY,
    ),
    (
        "recommendation_language",
        _graft("This looks like a perfect fit."),
        COVER_RECOMMENDATION,
    ),
    (
        "inflated_phrase",
        _graft("I am a results-driven engineer above all."),
        BANNED_PHRASE,
    ),
    ("not_english", INDONESIAN_NOTE, COVER_NOT_ENGLISH),
)


def _writer(
    session_factory: sessionmaker[Session], payload: dict[str, object]
) -> tuple[CoverWriter, FakeLLMClient]:
    llm = FakeLLMClient().repeat(payload)
    writer = CoverWriter(
        llm=llm,
        session_factory=session_factory,
        prompts_dir=PROMPTS_DIR,
        model="test-model",
    )
    return writer, llm


async def _run(
    session_factory: sessionmaker[Session], payload: dict[str, object]
) -> tuple[str | None, str | None, str | None, int, FakeLLMClient]:
    writer, llm = _writer(session_factory, payload)
    result = await writer.write(
        structure=STRUCTURE,
        results=RESULTS,
        cv_text=CV_TEXT,
        jd_text=JD_CLEAN,
    )
    return result.note.status, result.note.text, result.note.reason, len(llm.requests), llm


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
async def test_a_fabricated_note_is_never_returned(
    session_factory: sessionmaker[Session],
    label: str,
    text: str,
    expected: str,
) -> None:
    payload = {"text": text, "asserted_requirement_indexes": [0, 1]}

    status, returned, reason, calls, _ = await _run(session_factory, payload)

    assert returned is None, label
    assert status == f"rejected_{expected}", label
    assert reason is not None
    assert calls == 2, "one rejection is retried exactly once"


async def test_the_retry_is_told_which_rule_it_broke(
    session_factory: sessionmaker[Session],
) -> None:
    payload = {
        "text": _graft("Settlement finishes 94 percent faster now."),
        "asserted_requirement_indexes": [0, 1],
    }

    _, _, reason, _, llm = await _run(session_factory, payload)

    assert reason is not None
    assert "94" in llm.requests[-1].user
    assert "rejected" in llm.requests[-1].user


async def test_a_faithful_note_still_passes(
    session_factory: sessionmaker[Session],
) -> None:
    status, returned, reason, calls, _ = await _run(session_factory, COVER_OK)

    assert status == "pass"
    assert returned == COVER_TEXT
    assert reason is None
    assert calls == 1, "a passing note is not retried"
