"""Constraint flags: the user's non-negotiables against what the post states.

Deterministic, informational, and never a gate: a conflict is reported next to
the summary, it does not skip a job or change a verdict. Every rule is a
function in one list, so a new constraint is a new function, not an edit here.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.modules.analysis.schemas import JdStructure
from app.shared.text import normalise

STATUS_OK: Final = "ok"
STATUS_CONFLICT: Final = "conflict"
STATUS_REVIEW: Final = "review"
STATUS_NOT_STATED: Final = "not_stated"

KIND_WORK_MODE: Final = "work_mode"
KIND_LOCATIONS: Final = "locations"
KIND_LANGUAGES: Final = "languages"
KIND_SALARY: Final = "salary"
KIND_WORK_AUTHORIZATION: Final = "work_authorization"


@dataclass(frozen=True, slots=True)
class UserConstraints:
    """A snapshot of the settings the analysis module is allowed to see."""

    languages: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()
    salary_floor_amount: float | None = None
    salary_floor_currency: str | None = None
    work_authorization: str | None = None

    def floor_text(self) -> str | None:
        if self.salary_floor_amount is None:
            return None
        currency = self.salary_floor_currency or ""
        return f"{self.salary_floor_amount:g} {currency}".strip()


@dataclass(frozen=True, slots=True)
class ConstraintFlag:
    kind: str
    status: str
    note: str
    jd_value: str | None = None
    user_value: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "note": self.note,
            "jd_value": self.jd_value,
            "user_value": self.user_value,
        }


Rule = Callable[[UserConstraints, JdStructure], ConstraintFlag]


def _join(values: Sequence[str]) -> str | None:
    cleaned = [value.strip() for value in values if value.strip()]
    return ", ".join(cleaned) if cleaned else None


def _overlaps(first: str, second: str) -> bool:
    """Loose match: "Berlin, Germany" overlaps "Berlin", "EU" does not."""
    left = normalise(first)
    right = normalise(second)
    if not left or not right:
        return False
    return left in right or right in left


def rule_work_mode(user: UserConstraints, jd: JdStructure) -> ConstraintFlag:
    mode = (jd.work_mode or "unknown").strip().lower()
    wanted = _join(user.work_modes)
    if mode in ("", "unknown"):
        return ConstraintFlag(
            kind=KIND_WORK_MODE,
            status=STATUS_NOT_STATED,
            note="The post does not state a work mode.",
            user_value=wanted,
        )
    if not user.work_modes:
        return ConstraintFlag(
            kind=KIND_WORK_MODE,
            status=STATUS_REVIEW,
            note=f"The post says {mode}; you have not stated which modes you accept.",
            jd_value=mode,
        )
    if mode in user.work_modes:
        return ConstraintFlag(
            kind=KIND_WORK_MODE,
            status=STATUS_OK,
            note=f"The post says {mode}, which you accept.",
            jd_value=mode,
            user_value=wanted,
        )
    return ConstraintFlag(
        kind=KIND_WORK_MODE,
        status=STATUS_CONFLICT,
        note=f"The post says {mode}; you accept {wanted}.",
        jd_value=mode,
        user_value=wanted,
    )


def rule_locations(user: UserConstraints, jd: JdStructure) -> ConstraintFlag:
    location = (jd.location or "").strip()
    wanted = _join(user.locations)
    mode = (jd.work_mode or "").strip().lower()
    if not location:
        return ConstraintFlag(
            kind=KIND_LOCATIONS,
            status=STATUS_NOT_STATED,
            note="The post does not state a location.",
            user_value=wanted,
        )
    if not user.locations:
        return ConstraintFlag(
            kind=KIND_LOCATIONS,
            status=STATUS_REVIEW,
            note=f"The post is in {location}; you have not stated which locations you accept.",
            jd_value=location,
        )
    status, note = _location_verdict(location, wanted, mode, user.locations)
    return ConstraintFlag(
        kind=KIND_LOCATIONS,
        status=status,
        note=note,
        jd_value=location,
        user_value=wanted,
    )


def _location_verdict(
    location: str, wanted: str | None, mode: str, accepted: Sequence[str]
) -> tuple[str, str]:
    """Remote outranks a city match: the city you accept still applies loosely."""
    if mode == "remote":
        return (
            STATUS_OK,
            f"The post is remote ({location}), so the location you listed applies loosely.",
        )
    if any(_overlaps(location, candidate) for candidate in accepted):
        return STATUS_OK, f"The post is in {location}, which you accept."
    return STATUS_CONFLICT, f"The post is in {location}; you listed {wanted}."


def rule_languages(user: UserConstraints, jd: JdStructure) -> ConstraintFlag:
    languages = [language for language in jd.languages if language.strip()]
    wanted = _join(user.languages)
    if not languages:
        return ConstraintFlag(
            kind=KIND_LANGUAGES,
            status=STATUS_NOT_STATED,
            note="The post does not state a language requirement.",
            user_value=wanted,
        )
    stated = ", ".join(languages)
    if not user.languages:
        return ConstraintFlag(
            kind=KIND_LANGUAGES,
            status=STATUS_REVIEW,
            note=f"The post asks for {stated}; you have not listed your languages.",
            jd_value=stated,
        )
    if any(
        _overlaps(language, candidate) for language in languages for candidate in user.languages
    ):
        return ConstraintFlag(
            kind=KIND_LANGUAGES,
            status=STATUS_OK,
            note=f"The post asks for {stated}; you listed {wanted}.",
            jd_value=stated,
            user_value=wanted,
        )
    return ConstraintFlag(
        kind=KIND_LANGUAGES,
        status=STATUS_CONFLICT,
        note=f"The post asks for {stated}; you listed {wanted}.",
        jd_value=stated,
        user_value=wanted,
    )


def rule_salary(user: UserConstraints, jd: JdStructure) -> ConstraintFlag:
    floor = user.floor_text()
    stated = (jd.salary_text or "").strip()
    if floor is None:
        return ConstraintFlag(
            kind=KIND_SALARY,
            status=STATUS_NOT_STATED,
            note="You have not set a salary floor.",
        )
    if not stated:
        return ConstraintFlag(
            kind=KIND_SALARY,
            status=STATUS_NOT_STATED,
            note="The post does not state pay.",
            user_value=floor,
        )
    # Pay arrives as prose with ranges, currencies and bonus schemes; comparing
    # it in code would be a guess, so it is handed to the user as stated.
    return ConstraintFlag(
        kind=KIND_SALARY,
        status=STATUS_REVIEW,
        note="The post states pay in prose; compare it with your floor yourself.",
        jd_value=stated,
        user_value=floor,
    )


def rule_work_authorization(user: UserConstraints, jd: JdStructure) -> ConstraintFlag:
    stated = (jd.work_authorization_text or "").strip()
    wanted = (user.work_authorization or "").strip() or None
    if wanted is None:
        return ConstraintFlag(
            kind=KIND_WORK_AUTHORIZATION,
            status=STATUS_NOT_STATED,
            note="You have not stated a work authorization requirement.",
        )
    if not stated:
        return ConstraintFlag(
            kind=KIND_WORK_AUTHORIZATION,
            status=STATUS_NOT_STATED,
            note="The post does not mention work authorization.",
            user_value=wanted,
        )
    if _overlaps(stated, wanted):
        return ConstraintFlag(
            kind=KIND_WORK_AUTHORIZATION,
            status=STATUS_OK,
            note="The post's authorization wording matches what you stated.",
            jd_value=stated,
            user_value=wanted,
        )
    return ConstraintFlag(
        kind=KIND_WORK_AUTHORIZATION,
        status=STATUS_REVIEW,
        note="The post states an authorization requirement in prose; check it yourself.",
        jd_value=stated,
        user_value=wanted,
    )


CONSTRAINT_RULES: Final[tuple[Rule, ...]] = (
    rule_work_mode,
    rule_locations,
    rule_languages,
    rule_salary,
    rule_work_authorization,
)


def build_flags(user: UserConstraints, jd: JdStructure) -> list[dict[str, Any]]:
    return [rule(user, jd).as_dict() for rule in CONSTRAINT_RULES]
