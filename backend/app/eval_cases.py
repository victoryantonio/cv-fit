"""Loading the eval set: case files in, labelled cases out. No pipeline here.

A case without a gold file is a mistake in the set, not a skipped case, so every
loader failure raises `EvalError` and stops the run.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# pyyaml ships no stubs and the eval set is my own files, not untrusted input.
# The error code is disabled for the module because an inline ignore on the
# import flips between "unused" and "needed" across mypy's incremental runs.
# mypy: disable-error-code="import-untyped"
import yaml
from docx import Document

from app.eval_metrics import REFUSALS, EvalError
from app.modules.analysis.enums import Verdict


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    cv_text: str
    jd_text: str
    title: str
    company: str | None
    gold: list[tuple[str, str]]
    expect: str = "analysis"


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvalError(f"Cannot read {path.name}: {exc}") from exc


def _gold_items(path: Path, *, expect: str = "analysis") -> list[tuple[str, str]]:
    raw = _load_yaml(path) or {}
    items: list[tuple[str, str]] = []
    for entry in raw.get("requirements") or []:
        text = str(entry.get("text") or "")
        verdict = str(entry.get("verdict") or "")
        if verdict not in tuple(Verdict):
            raise EvalError(f"{path.name}: unknown verdict {verdict!r} for {text!r}")
        items.append((text, verdict))
    # A page that must be refused has nothing to label, and an empty label file
    # would otherwise read as a forgotten one.
    if not items and expect == "analysis":
        raise EvalError(f"{path.name} has no requirements")
    return items


def load_cases(directory: Path, *, limit: int | None = None) -> list[Case]:
    """A case without a gold file is a mistake in the set, not a skipped case."""
    cases_dir = directory / "cases"
    if not cases_dir.is_dir():
        raise EvalError(f"No cases directory at {cases_dir}")
    # Recursive on purpose: the local pairs live in cases/local/ and are ignored
    # by git, so the set I actually run is never the set that shipped.
    files = sorted(path for path in cases_dir.rglob("*.yaml") if path.is_file())
    if limit is not None:
        files = files[:limit]
    if not files:
        raise EvalError(f"No *.yaml cases in {cases_dir}")
    cases: list[Case] = []
    for path in files:
        raw = _load_yaml(path)
        if not isinstance(raw, dict):
            raise EvalError(f"{path.name} must be a mapping")
        gold_path = directory / "gold" / path.relative_to(cases_dir)
        if not gold_path.is_file():
            raise EvalError(f"{path.name} has no gold labels at {gold_path}")
        expect = str(raw.get("expect") or "analysis")
        if expect != "analysis" and expect not in REFUSALS:
            raise EvalError(f"{path.name}: unknown expectation {expect!r}")
        cases.append(
            Case(
                case_id=str(raw.get("id") or path.stem),
                cv_text=str(raw.get("cv") or ""),
                jd_text=str(raw.get("jd") or ""),
                title=str(raw.get("title") or path.stem),
                company=str(raw["company"]) if raw.get("company") else None,
                gold=_gold_items(gold_path, expect=expect),
                expect=expect,
            )
        )
    return cases


def docx_bytes(text: str) -> bytes:
    """The intake path reads documents, so the case text travels as one."""
    buffer = io.BytesIO()
    document = Document()
    for line in text.splitlines() or [""]:
        document.add_paragraph(line)
    document.save(buffer)
    return buffer.getvalue()
