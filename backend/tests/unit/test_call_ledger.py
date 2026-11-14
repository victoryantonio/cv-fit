"""The ledger that links stored LLM calls to the analysis they produced.

D11: `record_call` used to write `analysis_id = NULL` forever, because the row it
points at does not exist until S9. These tests pin the bookkeeping; the
end-to-end link is asserted in `tests/integration/test_analysis.py`.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy.orm import Session

from app.modules.analysis import call_ledger


def test_a_run_collects_the_calls_it_records() -> None:
    with call_ledger.ledger() as calls:
        call_ledger.note("c1")
        call_ledger.note("c2")
        assert calls.pending == ["c1", "c2"]


def test_a_known_analysis_outranks_the_callers_hint() -> None:
    """Regeneration owns its analysis id, so no hint can point elsewhere."""
    with call_ledger.ledger(analysis_id="a1"):
        assert call_ledger.analysis_for(None) == "a1"
        assert call_ledger.analysis_for("a2") == "a1"
    assert call_ledger.analysis_for("a2") == "a2"


def test_nothing_is_collected_outside_a_run() -> None:
    call_ledger.note("c1")  # must not raise, and must not be remembered

    assert call_ledger.analysis_for(None) is None


def test_attaching_nothing_changes_nothing() -> None:
    session = cast(Session, None)

    assert call_ledger.attach(session, [], analysis_id="a1") == 0


def test_the_ledger_is_reset_even_when_the_run_raises() -> None:
    try:
        with call_ledger.ledger() as calls:
            call_ledger.note("c1")
            raise RuntimeError("pipeline failed")
    except RuntimeError:
        pass

    assert calls.pending == ["c1"]
    assert call_ledger.analysis_for(None) is None
