"""Committed schema snapshots must match the models, byte for byte."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.analysis.schemas import (
    SCHEMA_MODELS,
    render_schema,
    snapshot_dir,
    write_schema_snapshots,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"


@pytest.mark.parametrize("name", sorted(SCHEMA_MODELS))
def test_committed_snapshot_matches_the_model(name: str) -> None:
    path = snapshot_dir(PROMPTS_DIR) / f"{name}.json"

    assert path.is_file(), f"missing snapshot: {path}. Run: uv run python -m app.cli export-schemas"
    assert path.read_text(encoding="utf-8") == render_schema(name), (
        f"{name} snapshot is stale. Run: uv run python -m app.cli export-schemas"
    )


def test_snapshots_are_written_deterministically(tmp_path: Path) -> None:
    first = {
        path.name: path.read_text(encoding="utf-8") for path in write_schema_snapshots(tmp_path)
    }
    second = {
        path.name: path.read_text(encoding="utf-8") for path in write_schema_snapshots(tmp_path)
    }

    assert first == second


def test_every_snapshot_is_valid_json(tmp_path: Path) -> None:
    import json

    for path in write_schema_snapshots(tmp_path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["type"] == "object"
        assert payload["additionalProperties"] is False
