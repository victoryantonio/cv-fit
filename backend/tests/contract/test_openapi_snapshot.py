"""The committed OpenAPI file must match the app it was generated from.

`frontend/src/api/schema.d.ts` is generated from that file, so a stale file
means a stale client: the UI would compile against routes or fields the backend
no longer serves. Regenerate with `python -m app.cli openapi`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.container import Container
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = REPO_ROOT / "frontend" / "openapi.json"


def test_committed_openapi_matches_the_app(container: Container) -> None:
    assert SPEC_PATH.is_file(), (
        f"{SPEC_PATH} is missing. Generate it with: python -m app.cli openapi"
    )
    committed = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    current = create_app(container).openapi()
    assert committed == current, (
        "frontend/openapi.json is stale. Regenerate with: python -m app.cli openapi"
    )
