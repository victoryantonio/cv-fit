"""Constraint flags: deterministic, informational, and never a gate."""

from __future__ import annotations

from collections.abc import Sequence

from app.modules.analysis.constraints import (
    CONSTRAINT_RULES,
    ConstraintFlag,
    UserConstraints,
    build_flags,
    rule_languages,
    rule_locations,
    rule_salary,
    rule_work_authorization,
    rule_work_mode,
)
from app.modules.analysis.schemas import JdRequirementOut, JdStructure

REQUIREMENT = JdRequirementOut(
    text="Five years of Python",
    jd_quote="5+ years of Python.",
)


def _jd(
    *,
    work_mode: str = "unknown",
    location: str | None = None,
    languages: Sequence[str] = (),
    salary_text: str | None = None,
    work_authorization_text: str | None = None,
) -> JdStructure:
    return JdStructure(
        work_mode=work_mode,  # type: ignore[arg-type]
        location=location,
        languages=list(languages),
        salary_text=salary_text,
        work_authorization_text=work_authorization_text,
        requirements=[REQUIREMENT],
    )


def _status(flag: ConstraintFlag) -> str:
    return flag.status


def test_work_mode_is_not_stated_when_the_post_says_nothing() -> None:
    flag = rule_work_mode(UserConstraints(work_modes=("remote",)), _jd())

    assert _status(flag) == "not_stated"
    assert flag.jd_value is None
    assert flag.user_value == "remote"


def test_work_mode_accepted_by_the_user_is_ok() -> None:
    flag = rule_work_mode(UserConstraints(work_modes=("remote", "hybrid")), _jd(work_mode="remote"))

    assert _status(flag) == "ok"
    assert flag.jd_value == "remote"


def test_work_mode_outside_the_users_list_is_a_conflict() -> None:
    flag = rule_work_mode(UserConstraints(work_modes=("remote",)), _jd(work_mode="onsite"))

    assert _status(flag) == "conflict"
    assert flag.jd_value == "onsite"
    assert flag.user_value == "remote"


def test_work_mode_without_a_user_preference_asks_for_review() -> None:
    flag = rule_work_mode(UserConstraints(), _jd(work_mode="hybrid"))

    assert _status(flag) == "review"


def test_missing_location_is_not_stated() -> None:
    flag = rule_locations(UserConstraints(locations=("Berlin",)), _jd())

    assert _status(flag) == "not_stated"


def test_remote_posting_makes_the_location_list_loose() -> None:
    """A remote post never conflicts on location, even in another country."""
    flag = rule_locations(
        UserConstraints(locations=("Berlin",)),
        _jd(work_mode="remote", location="Remote (EU)"),
    )

    assert _status(flag) == "ok"
    assert flag.jd_value == "Remote (EU)"


def test_location_overlap_counts_as_ok() -> None:
    flag = rule_locations(
        UserConstraints(locations=("Berlin",)), _jd(work_mode="onsite", location="Berlin, Germany")
    )

    assert _status(flag) == "ok"


def test_other_country_is_a_conflict() -> None:
    flag = rule_locations(
        UserConstraints(locations=("Berlin",)), _jd(work_mode="onsite", location="Lisbon, Portugal")
    )

    assert _status(flag) == "conflict"


def test_location_without_a_user_preference_asks_for_review() -> None:
    flag = rule_locations(UserConstraints(), _jd(location="Berlin"))

    assert _status(flag) == "review"


def test_languages() -> None:
    stated = _jd(languages=["English"])

    assert _status(rule_languages(UserConstraints(languages=("English",)), stated)) == "ok"
    assert _status(rule_languages(UserConstraints(languages=("German",)), stated)) == "conflict"
    assert _status(rule_languages(UserConstraints(), stated)) == "review"
    assert _status(rule_languages(UserConstraints(languages=("English",)), _jd())) == "not_stated"


def test_salary_is_never_compared_in_code() -> None:
    """Pay arrives as prose, so it is handed to the user as stated."""
    paid = _jd(salary_text="EUR 60,000 - 80,000 plus bonus")
    floor = UserConstraints(salary_floor_amount=70000, salary_floor_currency="EUR")

    without_floor = rule_salary(UserConstraints(), paid)
    without_pay = rule_salary(floor, _jd())
    with_both = rule_salary(floor, paid)

    assert _status(without_floor) == "not_stated"
    assert _status(without_pay) == "not_stated"
    assert without_pay.user_value == "70000 EUR"
    assert _status(with_both) == "review"
    assert with_both.jd_value == "EUR 60,000 - 80,000 plus bonus"


def test_work_authorization() -> None:
    stated = _jd(work_authorization_text="Must hold an EU work permit.")

    assert _status(rule_work_authorization(UserConstraints(), stated)) == "not_stated"
    assert (
        _status(
            rule_work_authorization(UserConstraints(work_authorization="EU work permit"), _jd())
        )
        == "not_stated"
    )
    assert (
        _status(
            rule_work_authorization(UserConstraints(work_authorization="EU work permit"), stated)
        )
        == "ok"
    )
    assert (
        _status(
            rule_work_authorization(UserConstraints(work_authorization="US citizen only"), stated)
        )
        == "review"
    )


def test_build_flags_covers_every_rule_in_order() -> None:
    flags = build_flags(
        UserConstraints(languages=("English",), locations=("Berlin",), work_modes=("remote",)),
        _jd(work_mode="remote", location="Berlin", languages=["English"]),
    )

    assert [flag["kind"] for flag in flags] == [
        "work_mode",
        "locations",
        "languages",
        "salary",
        "work_authorization",
    ]
    assert len(flags) == len(CONSTRAINT_RULES)
    assert all(isinstance(flag["note"], str) and flag["note"] for flag in flags)
