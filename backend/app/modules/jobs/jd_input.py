"""Heuristics for text pasted from a job page.

AGENTS.md treats pasted text as untrusted data, so instruction-like phrases are
detected only to *show* the user a flag (E08). A flag changes nothing: the real
defences are the delimiters in the prompt, no tools attached, and schema
validation. Truncation detection is advisory too (E27).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

MIN_JD_CHARS: Final = 200
MAX_JD_CHARS: Final = 60_000

FlagRule = Callable[[str], str | None]

_INSTRUCTION_OVERRIDE: Final = re.compile(
    r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}"
    r"\b(previous|prior|above|earlier|system)\b[^.\n]{0,30}"
    r"\b(instruction|instructions|prompt|direction|directions|rule|rules|message)\b",
    re.IGNORECASE,
)
_ROLE_ASSIGNMENT: Final = re.compile(
    r"\byou are (now |no longer )?(a|an|the)?\s*(system|assistant|ai|language model|chatbot)\b"
    r"|\b(act|behave|respond) as (a|an|the)\s*(system|assistant|ai|language model)\b",
    re.IGNORECASE,
)
_DELIMITER_ESCAPE: Final = re.compile(
    r"</?\s*(job_post|job_description|system|instructions?|prompt)\s*>"
    r"|\{\{|\}\}"
    r"|```\s*(json|xml|markdown)",
    re.IGNORECASE,
)
_OUTPUT_COMMAND: Final = re.compile(
    r"\b(return|respond|reply|output|print)\b[^.\n]{0,30}\b(json|exactly|verbatim|only)\b",
    re.IGNORECASE,
)
_HIDDEN_CHARS: Final = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_HTML_COMMENT: Final = re.compile(r"<!--|-->")


def rule_instruction_override(text: str) -> str | None:
    return "instruction_override" if _INSTRUCTION_OVERRIDE.search(text) else None


def rule_role_assignment(text: str) -> str | None:
    return "role_assignment" if _ROLE_ASSIGNMENT.search(text) else None


def rule_delimiter_escape(text: str) -> str | None:
    return "delimiter_escape" if _DELIMITER_ESCAPE.search(text) else None


def rule_output_command(text: str) -> str | None:
    return "output_command" if _OUTPUT_COMMAND.search(text) else None


def rule_hidden_characters(text: str) -> str | None:
    return "hidden_characters" if _HIDDEN_CHARS.search(text) else None


def rule_html_comment(text: str) -> str | None:
    return "html_comment" if _HTML_COMMENT.search(text) else None


INJECTION_RULES: Final[tuple[FlagRule, ...]] = (
    rule_instruction_override,
    rule_role_assignment,
    rule_delimiter_escape,
    rule_output_command,
    rule_hidden_characters,
    rule_html_comment,
)


def detect_injection(text: str) -> list[str]:
    """Flags in rule order, without duplicates."""
    flags = [flag for rule in INJECTION_RULES if (flag := rule(text)) is not None]
    return list(dict.fromkeys(flags))


COLLAPSED_MARKERS: Final[tuple[str, ...]] = (
    "…see more",
    "...see more",
    "see more",
    "show more",
    "show less",
    "read more",
    "show all",
    "… more",
    "... more",
)

_TERMINAL_CHARS: Final = ".!?:;\"'”’)]}%"
# A page cut by a "Read more" link usually stops on a joining word.
DANGLING_WORDS: Final[frozenset[str]] = frozenset(
    {
        "and",
        "or",
        "but",
        "with",
        "to",
        "for",
        "the",
        "a",
        "an",
        "of",
        "in",
        "on",
        "at",
        "by",
        "as",
        "from",
        "including",
        "plus",
    }
)

MIN_TAIL_CHARS: Final = 20


def rule_collapsed_marker(text: str) -> str | None:
    lowered = text.casefold()
    return "collapsed_marker" if any(marker in lowered for marker in COLLAPSED_MARKERS) else None


def _tail(text: str) -> str:
    for line in reversed(text.split("\n")):
        if line.strip():
            return line.strip()
    return ""


def rule_mid_sentence(text: str) -> str | None:
    tail = _tail(text)
    if len(tail) < MIN_TAIL_CHARS:
        return None
    if "|" in tail:
        # A pipe-separated row is a footer or nav strip, and those never end in a period.
        return None
    last = tail[-1]
    if last in _TERMINAL_CHARS:
        return None
    if not (last.isalnum() or last in ",-–"):
        return None
    return "mid_sentence"


def rule_dangling_word(text: str) -> str | None:
    tail = _tail(text)
    if not tail:
        return None
    last = tail.rstrip(".,;:-–").split()[-1].casefold()
    return "dangling_word" if last in DANGLING_WORDS else None


TRUNCATION_RULES: Final[tuple[FlagRule, ...]] = (
    rule_collapsed_marker,
    rule_mid_sentence,
    rule_dangling_word,
)


def detect_truncation(text: str) -> list[str]:
    """Reasons the pasted text may be cut off. Empty means nothing looked wrong."""
    reasons = [reason for rule in TRUNCATION_RULES if (reason := rule(text)) is not None]
    return list(dict.fromkeys(reasons))
