"""Redaction is the only thing standing between a CV and a third-party API."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from app.modules.cvs.redactor import RULES, RedactionResult, redact


def _no_pii_left(text: str, needles: Iterable[str]) -> None:
    for needle in needles:
        assert needle not in text, f"{needle!r} survived redaction"


def test_email_is_tokenised() -> None:
    result = redact("Contact rina.pratama@example.com today.")

    assert result.text == "Contact [EMAIL_1] today."
    assert result.counts == {"EMAIL": 1}


def test_repeated_emails_get_numbered_tokens() -> None:
    result = redact("a@example.com and b@example.org and a@example.com")

    assert result.text == "[EMAIL_1] and [EMAIL_2] and [EMAIL_3]"


@pytest.mark.parametrize(
    "phone",
    [
        "+62 812-3456-7890",
        "081234567890",
        "(021) 555-1234",
        "+1 415 555 0199",
    ],
)
def test_phone_numbers_are_tokenised(phone: str) -> None:
    result = redact(f"Call {phone} now")

    assert "PHONE" in result.text
    assert phone not in result.text


def test_date_ranges_are_not_phone_numbers() -> None:
    text = "Senior Backend Engineer, PT Contoh Jaya, 2021 - 2024"

    assert redact(text).text == text


def test_personal_urls_are_tokenised() -> None:
    result = redact("See https://github.com/rina-pratama and linkedin.com/in/rina-pratama")

    assert result.text == "See [URL_1] and [URL_2]"


def test_sixteen_digit_ids_are_tokenised() -> None:
    result = redact("NIK 3273012504950001 and 3273 0125 0495 0001")

    assert result.text == "NIK [ID_1] and [ID_2]"


def test_street_address_line_is_tokenised() -> None:
    result = redact("Jl. Melati No. 12, Bandung 40123\nPython, SQL")

    assert result.text == "[ADDRESS_1]\nPython, SQL"


def test_custom_terms_prefer_the_longest_match() -> None:
    result = redact(
        "Worked at PT Contoh Jaya on ledger work.", custom_terms=["Contoh", "PT Contoh Jaya"]
    )

    assert result.text == "Worked at [CUSTOM_1] on ledger work."


def test_custom_terms_are_case_insensitive() -> None:
    result = redact("ledger at pt contoh jaya", custom_terms=["PT Contoh Jaya"])

    assert result.text == "ledger at [CUSTOM_1]"


def test_rules_are_applied_in_declared_order() -> None:
    text = "email me at rina@example.com or call +62 812-3456-7890"
    counts: dict[str, int] = {}
    for rule in RULES:
        text = rule(text, counts)

    assert text == "email me at [EMAIL_1] or call [PHONE_1]"
    assert list(counts) == ["EMAIL", "PHONE"]


def test_redaction_is_stable() -> None:
    source = "Rina rina@example.com +62 812-3456-7890 Jl. Melati No. 12"

    assert redact(source) == redact(source)


def test_redaction_is_idempotent() -> None:
    once: RedactionResult = redact("Rina rina@example.com +62 812-3456-7890 Jl. Melati No. 12")

    assert redact(once.text).text == once.text


def test_realistic_cv_loses_contacts_but_keeps_content() -> None:
    source = (
        "RINA PRATAMA\n"
        "rina.pratama@example.com | +62 812-3456-7890\n"
        "Jl. Melati No. 12, Bandung 40123\n"
        "EXPERIENCE\n"
        "Rebuilt the settlement worker in Python and cut runtime from 40 to 6 minutes.\n"
    )

    result = redact(source)

    _no_pii_left(
        result.text,
        ["rina.pratama@example.com", "812-3456-7890", "Jl. Melati", "40123"],
    )
    assert "Rebuilt the settlement worker in Python" in result.text
    assert result.total == 3
