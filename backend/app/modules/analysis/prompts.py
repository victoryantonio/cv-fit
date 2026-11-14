"""Prompts live on disk, versioned by file name.

`prompt_bundle` is the SHA-256 over every prompt file plus every schema
snapshot, so a cache entry is invalidated by a one-byte edit anywhere.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.modules.analysis.schemas import SCHEMA_DIR_NAME

PROMPT_SUFFIXES = (".md", ".txt", ".json")


class PromptError(Exception):
    """A prompt file is missing or unreadable."""


@dataclass(frozen=True)
class PromptRef:
    name: str
    version: str
    bundle: str

    @property
    def prompt_version(self) -> str:
        return f"{self.name}.{self.version}"


@dataclass(frozen=True)
class PromptText:
    ref: PromptRef
    system: str
    user_template: str


def _prompt_files(prompts_dir: Path) -> list[Path]:
    if not prompts_dir.is_dir():
        raise PromptError(f"prompts directory not found: {prompts_dir}")
    files = [
        path for path in prompts_dir.rglob("*") if path.is_file() and path.suffix in PROMPT_SUFFIXES
    ]
    if not files:
        raise PromptError(f"no prompt files in {prompts_dir}")
    return sorted(files, key=lambda path: path.relative_to(prompts_dir).as_posix())


def compute_prompt_bundle(prompts_dir: Path) -> str:
    """Hash over sorted relative paths and their bytes."""
    digest = hashlib.sha256()
    for path in _prompt_files(prompts_dir):
        relative = path.relative_to(prompts_dir).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_prompt(prompts_dir: Path, name: str, version: str = "v1") -> PromptText:
    """Read `{name}.{version}.md`. The first `---` block is the system prompt."""
    path = prompts_dir / f"{name}.{version}.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"prompt file not readable: {path}") from exc
    system, _, user_template = raw.partition("\n---\n")
    if not user_template.strip():
        raise PromptError(f"prompt file has no user section (missing '---'): {path}")
    return PromptText(
        ref=PromptRef(name=name, version=version, bundle=compute_prompt_bundle(prompts_dir)),
        system=system.strip(),
        user_template=user_template.strip(),
    )


_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def fill(template: str, values: dict[str, str]) -> str:
    """Single-pass substitution so a value can never re-expand a placeholder."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise PromptError(f"missing prompt value: {key}")
        return values[key]

    return _PLACEHOLDER.sub(replace, template)


def schema_snapshot_names(prompts_dir: Path) -> list[str]:
    target = prompts_dir / SCHEMA_DIR_NAME
    if not target.is_dir():
        return []
    return sorted(path.stem for path in target.glob("*.json"))
