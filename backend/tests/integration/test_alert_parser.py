"""Alert parsing: known layouts parse, unknown layouts are reported (E05)."""

from __future__ import annotations

import email
import email.policy
from pathlib import Path

import pytest

from app.mcp_gmail.alert_parser import parse_alert

ALERTS = Path(__file__).resolve().parents[1] / "fixtures" / "alerts"


def _plain(path: Path) -> tuple[str, str]:
    with path.open("rb") as handle:
        message = email.message_from_binary_file(handle, policy=email.policy.default)
    body = message.get_body(preferencelist=("plain",))
    assert body is not None, f"{path.name} has no text/plain part"
    return str(message["Subject"]), body.get_content()


def _fixtures() -> list[Path]:
    found = sorted(ALERTS.glob("*.eml"))
    assert found, "alert fixtures are missing"
    return found


@pytest.mark.parametrize("path", _fixtures(), ids=lambda found: found.stem[:34])
def test_every_real_alert_parses_into_cards(path: Path) -> None:
    subject, body = _plain(path)
    result = parse_alert(subject=subject, body=body)
    assert result.layout == "linkedin_job_alert_digest"
    assert result.warnings == []
    assert result.cards
    for card in result.cards:
        assert card.title.strip()
        assert card.url is not None
        assert "/jobs/view/" in card.url


@pytest.mark.parametrize("path", _fixtures(), ids=lambda found: found.stem[:34])
def test_the_digest_header_never_becomes_a_card_title(path: Path) -> None:
    subject, body = _plain(path)
    for card in parse_alert(subject=subject, body=body).cards:
        lowered = card.title.lower()
        assert not lowered.startswith("your job alert for")
        assert "match your preferences" not in lowered
        assert not card.title.startswith("-")


def test_a_known_card_keeps_its_three_fields() -> None:
    path = next(found for found in _fixtures() if "Westpac" in found.name)
    subject, body = _plain(path)
    first = parse_alert(subject=subject, body=body).cards[0]
    assert first.title == "Senior AI Engineer - Intelligence & Protection"
    assert first.company == "Westpac"
    assert first.location == "Sydney, NSW"
    assert first.url is not None and "/jobs/view/" in first.url


def test_annotations_do_not_become_company_or_location() -> None:
    body = (
        "Your job alert for data engineer in Sydney\n"
        "5 new jobs match your preferences.\n\n"
        "Data Engineer\n"
        "Acme\n"
        "Sydney, NSW\n\n"
        "2 school alum\n"
        "1 connection\n"
        "This company is actively hiring\n"
        "View job: https://www.linkedin.com/comm/jobs/view/1/\n"
        "---------------------------------------------------------\n"
    )
    cards = parse_alert(subject="Data Engineer", body=body).cards
    assert len(cards) == 1
    assert (cards[0].title, cards[0].company, cards[0].location) == (
        "Data Engineer",
        "Acme",
        "Sydney, NSW",
    )


def test_a_card_without_a_company_keeps_what_it_has() -> None:
    body = (
        "Your job alert for platform engineer\n\n"
        "Platform Engineer\n"
        "View job: https://www.linkedin.com/comm/jobs/view/2/\n"
        "---------------\n"
    )
    cards = parse_alert(subject="Platform Engineer", body=body).cards
    assert len(cards) == 1
    assert cards[0].title == "Platform Engineer"
    assert cards[0].company is None
    assert cards[0].location is None


def test_an_unknown_layout_is_reported_not_dropped() -> None:
    result = parse_alert(subject="Weekly roundup", body="Here are some jobs we like.")
    assert result.layout is None
    assert result.cards == []
    assert result.recognized is False
    assert result.warnings == ["unknown alert layout"]


def test_a_recognized_digest_with_no_cards_says_so() -> None:
    result = parse_alert(
        subject="Your job alert for rust", body="Your job alert for rust\n\nNo jobs today.\n"
    )
    assert result.layout == "linkedin_job_alert_digest"
    assert result.cards == []
    assert result.warnings == ["no job card found in this email"]
