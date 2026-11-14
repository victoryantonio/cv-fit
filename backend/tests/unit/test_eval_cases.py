"""Reading the eval set, and turning one stored packet into an outcome.

The labels are mine, typed by hand, so the loader has to refuse a broken set
instead of quietly scoring zero against it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.eval_cli import EvalError, _outcomes, _unsupported, load_cases


def _payload(
    requirements: list[tuple[str, str]],
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "requirements": [{"id": key, "text": text} for key, text in requirements],
        "matches": matches or [],
        "suggestions": [],
        "cover_note": {"text": ""},
    }


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


CASE = """
id: one
title: Senior Backend Engineer
company: Acme Payments
cv: |
  RINA PRATAMA
jd: |
  We need Go.
"""

GOLD = """
requirements:
  - text: Strong Go
    verdict: strong
"""


def test_a_case_and_its_gold_file_are_loaded(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "one.yaml", CASE)
    _write(tmp_path / "gold" / "one.yaml", GOLD)

    cases = load_cases(tmp_path)

    assert [case.case_id for case in cases] == ["one"]
    assert cases[0].title == "Senior Backend Engineer"
    assert cases[0].company == "Acme Payments"
    assert cases[0].cv_text.startswith("RINA PRATAMA")
    assert cases[0].gold == [("Strong Go", "strong")]


def test_local_pairs_in_a_subdirectory_are_found(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "local" / "one.yaml", CASE)
    _write(tmp_path / "gold" / "local" / "one.yaml", GOLD)

    assert [case.case_id for case in load_cases(tmp_path)] == ["one"]


def test_a_case_without_gold_stops_the_run(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "one.yaml", CASE)

    with pytest.raises(EvalError, match="no gold labels"):
        load_cases(tmp_path)


def test_a_page_that_must_be_refused_needs_no_labels(tmp_path: Path) -> None:
    _write(
        tmp_path / "cases" / "local" / "nav.yaml",
        "id: nav\ntitle: LinkedIn jobs menu\nexpect: JD_NOT_FOUND\ncv: |\n  RINA\njd: |\n  Jobs\n",
    )
    _write(tmp_path / "gold" / "local" / "nav.yaml", "expect: JD_NOT_FOUND\n")

    cases = load_cases(tmp_path)

    assert cases[0].expect == "JD_NOT_FOUND"
    assert cases[0].gold == []


def test_an_unknown_expectation_is_a_broken_case(tmp_path: Path) -> None:
    _write(
        tmp_path / "cases" / "one.yaml",
        "id: one\ntitle: X\nexpect: JD_TOO_SHORT\ncv: |\n  RINA\njd: |\n  We need Go.\n",
    )
    _write(tmp_path / "gold" / "one.yaml", GOLD)

    with pytest.raises(EvalError, match="unknown expectation"):
        load_cases(tmp_path)


def test_a_pair_still_needs_an_expectation_of_analysis(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "one.yaml", CASE)
    _write(tmp_path / "gold" / "one.yaml", GOLD)

    assert load_cases(tmp_path)[0].expect == "analysis"


def test_an_unknown_verdict_is_a_broken_label_not_a_gap(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "one.yaml", CASE)
    _write(tmp_path / "gold" / "one.yaml", GOLD.replace("strong", "probably"))

    with pytest.raises(EvalError, match="unknown verdict"):
        load_cases(tmp_path)


def test_a_limit_takes_the_first_cases_in_order(tmp_path: Path) -> None:
    for name in ("a", "b"):
        _write(tmp_path / "cases" / f"{name}.yaml", CASE.replace("id: one", f"id: {name}"))
        _write(tmp_path / "gold" / f"{name}.yaml", GOLD)

    assert [case.case_id for case in load_cases(tmp_path, limit=1)] == ["a"]


def test_an_empty_set_is_an_error_not_a_perfect_score(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "README.md", "nothing here")

    with pytest.raises(EvalError, match="No .*cases"):
        load_cases(tmp_path)


def test_a_gold_file_without_requirements_is_an_error(tmp_path: Path) -> None:
    _write(tmp_path / "cases" / "one.yaml", CASE)
    _write(tmp_path / "gold" / "one.yaml", "requirements: []\n")

    with pytest.raises(EvalError, match="no requirements"):
        load_cases(tmp_path)


def test_a_quote_the_cv_does_not_contain_is_ungrounded() -> None:
    payload = _payload(
        [("r1", "Strong Go")],
        [
            {
                "requirement_id": "r1",
                "verdict": "strong",
                "evidence_quote": "Ten years of Kubernetes",
                "votes": {"strong": 3},
            }
        ],
    )

    outcomes, matched = _outcomes(payload, [("Strong Go", "strong")], "I write Go.")

    assert matched == 1
    assert outcomes[0].grounded is False


def test_a_quote_taken_from_the_cv_is_grounded() -> None:
    payload = _payload(
        [("r1", "Strong Go")],
        [
            {
                "requirement_id": "r1",
                "verdict": "strong",
                "evidence_quote": "I write Go.",
                "votes": {"strong": 3},
            }
        ],
    )

    outcomes, _ = _outcomes(payload, [("Strong Go", "strong")], "I write Go.")

    assert outcomes[0].grounded is True


def test_a_gap_needs_no_quote_to_be_grounded() -> None:
    payload = _payload(
        [("r1", "Kubernetes")],
        [
            {
                "requirement_id": "r1",
                "verdict": "gap",
                "evidence_quote": None,
                "votes": {"gap": 3},
            }
        ],
    )

    outcomes, _ = _outcomes(payload, [("Kubernetes", "gap")], "I write Go.")

    assert outcomes[0].grounded is True


def test_a_strong_verdict_with_no_quote_at_all_is_ungrounded() -> None:
    payload = _payload(
        [("r1", "Strong Go")],
        [{"requirement_id": "r1", "verdict": "strong", "evidence_quote": None, "votes": {}}],
    )

    outcomes, _ = _outcomes(payload, [("Strong Go", "strong")], "I write Go.")

    assert outcomes[0].grounded is False


def test_a_requirement_that_was_never_extracted_has_no_verdict() -> None:
    payload = _payload([("r1", "Strong Go")], [])

    outcomes, matched = _outcomes(payload, [("Kubernetes", "strong")], "I write Go.")

    assert matched == 0
    assert outcomes[0].verdict is None


def test_a_number_that_is_not_in_the_cv_is_unsupported() -> None:
    payload = _payload([("r1", "Strong Go")])
    payload["suggestions"] = [{"proposed_text": "Cut latency by 40 percent."}]

    assert _unsupported(payload, "Cut latency from 900 ms to 240 ms.") == 1


def test_a_number_copied_from_the_cv_is_supported() -> None:
    payload = _payload([("r1", "Strong Go")])
    payload["suggestions"] = [{"proposed_text": "Cut p99 from 900 ms to 240 ms."}]
    payload["cover_note"] = {"text": "I run Go services."}

    assert _unsupported(payload, "Cut p99 latency from 900 ms to 240 ms.") == 0


def test_the_cover_note_is_checked_too() -> None:
    payload = _payload([("r1", "Strong Go")])
    payload["cover_note"] = {"text": "I led a team of 12 engineers."}

    assert _unsupported(payload, "I write Go.") == 1
