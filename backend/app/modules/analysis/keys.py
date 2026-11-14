"""The keys that decide whether a packet can be reused.

A key changes when anything that can change the stored packet changes: the CV
text, the requirement set, the prompt set, the model, the run count, and the
cover-note word bounds. Anything else is not part of the key on purpose, so a
settings tweak that cannot alter the output does not cost a model call.
"""

from __future__ import annotations

import json
from typing import Any

from app.modules.analysis.cover import CoverWriter
from app.modules.analysis.views import extraction_key
from app.shared.text import sha256_hex


def params_for(cover_writer: CoverWriter) -> dict[str, Any]:
    """Only the settings that can change the stored packet belong in the key."""
    return {
        "cover_min_words": cover_writer.min_words,
        "cover_max_words": cover_writer.max_words,
    }


def cache_key(
    *,
    cv_text_sha256: str,
    extract_key: str,
    prompt_bundle: str,
    model: str,
    runs: int,
    params: dict[str, Any] | None = None,
) -> str:
    """One key per (CV text, requirement set, prompt set, model, runs, params).

    `extract_key` rather than the extraction row id: the key has to be knowable
    from the stored snapshot alone, before S1 spends a token.
    """
    extra = json.dumps(params or {}, sort_keys=True, separators=(",", ":"))
    parts = [cv_text_sha256, extract_key, prompt_bundle, model, f"runs={runs}", extra]
    return sha256_hex("|".join(parts))


def analysis_key(
    *,
    cv: dict[str, Any],
    snapshot: dict[str, Any],
    match_bundle: str,
    model: str,
    runs: int,
    cover_writer: CoverWriter,
    params: dict[str, Any] | None = None,
) -> str:
    """The key for one CV version against one JD snapshot."""
    return cache_key(
        cv_text_sha256=str(cv["text_sha256"]),
        extract_key=extraction_key(
            text_sha256=str(snapshot["text_sha256"]),
            prompt_bundle=match_bundle,
            model=model,
        ),
        prompt_bundle=match_bundle,
        model=model,
        runs=runs,
        params=params_for(cover_writer) if params is None else params,
    )
