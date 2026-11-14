"""Effective model-provider configuration, shared by settings and the LLM client.

It lives in `shared` because the settings module produces it and the analysis
module consumes it, and modules may not import each other directly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LlmRuntime:
    base_url: str
    model: str
    api_key: str | None = None
    temperature: float = 0.2
    runs: int = 3

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
