"""The CLI export: one stored packet in, one Markdown file out.

The pipeline, the database and the network are all out of scope here; what is
checked is that the command writes the file it promises and that the file is the
same renderer the API serves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app import cli
from app.shared.errors import AppError

ANALYSIS_ID = "a1"

PAYLOAD: dict[str, Any] = {
    "id": ANALYSIS_ID,
    "status": "done",
    "model": "deepseek-v4-flash",
    "prompt_bundle": "abc123",
    "match_runs": 3,
    "created_at": "2026-01-01T00:00:00",
    "job": {"title": "Senior Backend Engineer", "company": "Acme Payments"},
    "requirements": [
        {
            "id": "r1",
            "position": 0,
            "text": "Five or more years of Python",
            "importance": "knockout",
            "active": True,
        }
    ],
    "matches": [
        {
            "requirement_id": "r1",
            "verdict": "strong",
            "evidence_quote": "Rebuilt the settlement worker in Python.",
        }
    ],
    "summary": {
        "label": "strong_fit",
        "coverage": 100,
        "counts": {"strong": 1, "partial": 0, "gap": 0},
        "must_have": {"met": 1, "total": 1, "coverage": 1.0},
        "knockout_gaps": [],
        "constraint_flags": [],
        "unstable_count": 0,
    },
    "suggestions": [],
    "suggestion_provenance": {"total": 0, "visible": 0, "hidden": 0, "rejected_by_rule": {}},
    "cover_note": {
        "text": "I am writing about the role.",
        "generated": "I am writing about the role.",
        "edited": None,
        "guard_status": "pass",
        "guard_reason": None,
        "is_draft": True,
        "word_count": 6,
    },
}


class StubAnalysis:
    """Honors the one method the command calls."""

    def get(self, analysis_id: str, include_rejected: bool = False) -> dict[str, Any]:
        assert analysis_id == ANALYSIS_ID
        assert include_rejected is False
        return PAYLOAD


class StubContainer:
    analysis = StubAnalysis()


def test_the_packet_command_writes_the_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "build_container", StubContainer)
    target = tmp_path / "packet.md"

    code = cli.main(["packet", "--analysis-id", ANALYSIS_ID, "--md", str(target)])

    assert code == 0
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Application packet: Senior Backend Engineer at Acme Payments")
    assert "## Cover note (draft)" in text
    assert "I am writing about the role." in text
    assert Path(json.loads(capsys.readouterr().out)["written"]) == target.resolve()


def test_the_export_needs_a_real_analysis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Missing(StubAnalysis):
        def get(self, analysis_id: str, include_rejected: bool = False) -> dict[str, Any]:
            raise AppError(
                "NOT_FOUND", "That analysis does not exist.", {"analysis_id": analysis_id}
            )

    class Container(StubContainer):
        analysis = Missing()

    monkeypatch.setattr(cli, "build_container", Container)
    target = tmp_path / "packet.md"

    code = cli.main(["packet", "--analysis-id", ANALYSIS_ID, "--md", str(target)])

    assert code == 1
    assert not target.exists()
    assert "NOT_FOUND" in capsys.readouterr().out
