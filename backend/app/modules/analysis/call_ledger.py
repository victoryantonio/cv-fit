"""Attach stored LLM calls to the analysis they paid for.

S1 and S2 spend tokens before the analysis row exists, so `llm_call.analysis_id`
cannot be filled at insert time: the row it points at is created at S9. Each
pipeline run therefore opens a ledger, every recorded call appends its row id,
and S9 writes the link once the analysis has an id.

Without this, `calls_for_analysis()` returns nothing for every packet, so the
token and latency figures read zero and M6 / NFR-04 cannot be measured at all.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db import new_id
from app.modules.analysis.models import LlmCall
from app.modules.analysis.ports import LlmRequest


@dataclass(slots=True)
class CallLedger:
    """Calls made by the run that is in progress."""

    analysis_id: str | None = None
    pending: list[str] = field(default_factory=list)


_CURRENT: ContextVar[CallLedger | None] = ContextVar("cv_fit_call_ledger", default=None)


@contextmanager
def ledger(analysis_id: str | None = None) -> Iterator[CallLedger]:
    """Collect the calls made inside the block.

    A ContextVar, not a parameter: the four step objects are injected singletons
    shared by concurrent runs, so a per-run value cannot live on them.
    """
    current = CallLedger(analysis_id=analysis_id)
    token = _CURRENT.set(current)
    try:
        yield current
    finally:
        _CURRENT.reset(token)


def analysis_for(explicit: str | None) -> str | None:
    """The analysis a call belongs to, preferring the one the run already knows."""
    current = _CURRENT.get()
    if current is not None and current.analysis_id is not None:
        return current.analysis_id
    return explicit


def note(call_id: str) -> None:
    """Remember a call whose analysis id is not known yet."""
    current = _CURRENT.get()
    if current is not None:
        current.pending.append(call_id)


def attach(session: Session, call_ids: list[str], *, analysis_id: str) -> int:
    """Link recorded calls to the analysis that owns them. Returns rows changed."""
    if not call_ids:
        return 0
    result = session.execute(
        update(LlmCall)
        .where(LlmCall.id.in_(call_ids), LlmCall.analysis_id.is_(None))
        .values(analysis_id=analysis_id)
    )
    return int(result.rowcount or 0)


def record_call(
    session: Session,
    *,
    request: LlmRequest,
    model: str,
    outcome: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    cache_hit: bool = False,
    analysis_id: str | None = None,
) -> None:
    """Store call metadata, and remember it if its analysis does not exist yet."""
    # The id is set here rather than by the column default, because the ledger
    # needs it before the flush that would assign it.
    call = LlmCall(
        id=new_id(),
        analysis_id=analysis_for(analysis_id),
        step=request.step,
        model=model,
        prompt_version=request.prompt_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        outcome=outcome,
    )
    session.add(call)
    note(call.id)

