"""A one-byte prompt edit must invalidate the cache. That is the whole point."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.analysis.prompts import (
    PromptError,
    compute_prompt_bundle,
    fill,
    load_prompt,
    schema_snapshot_names,
)
from app.modules.analysis.schemas import write_schema_snapshots

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"


def _mini_prompts(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "match.v1.md").write_text("system text\n---\nuser text\n", encoding="utf-8")
    (root / "suggest.v1.md").write_text("system text\n---\nuser text\n", encoding="utf-8")
    return root


def test_bundle_is_stable_for_unchanged_files(tmp_path: Path) -> None:
    root = _mini_prompts(tmp_path / "prompts")
    assert compute_prompt_bundle(root) == compute_prompt_bundle(root)


def test_one_byte_change_changes_the_bundle(tmp_path: Path) -> None:
    root = _mini_prompts(tmp_path / "prompts")
    before = compute_prompt_bundle(root)
    (root / "match.v1.md").write_text("system text\n---\nuser texT\n", encoding="utf-8")
    assert compute_prompt_bundle(root) != before


def test_file_order_does_not_change_the_bundle(tmp_path: Path) -> None:
    first = _mini_prompts(tmp_path / "a")
    second = tmp_path / "b"
    second.mkdir()
    (second / "suggest.v1.md").write_text("system text\n---\nuser text\n", encoding="utf-8")
    (second / "match.v1.md").write_text("system text\n---\nuser text\n", encoding="utf-8")

    assert compute_prompt_bundle(first) == compute_prompt_bundle(second)


def test_schema_snapshots_are_part_of_the_bundle(tmp_path: Path) -> None:
    root = _mini_prompts(tmp_path / "prompts")
    before = compute_prompt_bundle(root)
    write_schema_snapshots(root)
    assert compute_prompt_bundle(root) != before
    assert "match_verdict" in schema_snapshot_names(root)


def test_missing_directory_is_a_prompt_error(tmp_path: Path) -> None:
    with pytest.raises(PromptError):
        compute_prompt_bundle(tmp_path / "absent")


def test_load_prompt_splits_system_and_user(tmp_path: Path) -> None:
    root = _mini_prompts(tmp_path / "prompts")
    prompt = load_prompt(root, "match", "v1")

    assert prompt.system == "system text"
    assert prompt.user_template == "user text"
    assert prompt.ref.prompt_version == "match.v1"
    assert len(prompt.ref.bundle) == 64


def test_load_prompt_rejects_a_file_without_a_user_section(tmp_path: Path) -> None:
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "broken.v1.md").write_text("only a system prompt", encoding="utf-8")

    with pytest.raises(PromptError):
        load_prompt(root, "broken", "v1")


def test_load_prompt_rejects_a_missing_file(tmp_path: Path) -> None:
    root = _mini_prompts(tmp_path / "prompts")
    with pytest.raises(PromptError):
        load_prompt(root, "absent", "v1")


def test_fill_does_not_re_expand_placeholders(tmp_path: Path) -> None:
    assert fill("a {{x}} b", {"x": "{{y}}", "y": "boom"}) == "a {{y}} b"


@pytest.mark.parametrize("name", ["jd_structure", "match", "suggest", "cover_note"])
def test_committed_prompts_load(name: str) -> None:
    prompt = load_prompt(PROMPTS_DIR, name, "v1")

    assert prompt.system
    assert "{{" in prompt.user_template
