"""The pipeline steps, re-exported under one name.

S1 lives in `structurer`, S2..S4 in `matcher`, and the values they exchange in
`views`. This module is the import site callers already use, so the split stays
invisible to them.
"""

from __future__ import annotations

from app.modules.analysis.call_ledger import record_call
from app.modules.analysis.matcher import (
    MATCH_PROMPT,
    MATCH_PROMPT_VERSION,
    MATCH_SCHEMA,
    Matcher,
    MatchResult,
)
from app.modules.analysis.structure_rules import MAX_REQUIREMENTS, MIN_EXPECTED_REQUIREMENTS
from app.modules.analysis.structurer import (
    PROMPT_NAME,
    PROMPT_VERSION,
    SCHEMA_NAME,
    JdStructurer,
)
from app.modules.analysis.views import (
    IMPORTANCE_ORDER,
    RequirementView,
    StructuredJd,
    extraction_key,
)

__all__ = [
    "IMPORTANCE_ORDER",
    "MATCH_PROMPT",
    "MATCH_PROMPT_VERSION",
    "MATCH_SCHEMA",
    "MAX_REQUIREMENTS",
    "MIN_EXPECTED_REQUIREMENTS",
    "PROMPT_NAME",
    "PROMPT_VERSION",
    "SCHEMA_NAME",
    "JdStructurer",
    "MatchResult",
    "Matcher",
    "RequirementView",
    "StructuredJd",
    "extraction_key",
    "record_call",
]
