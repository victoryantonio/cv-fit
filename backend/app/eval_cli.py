"""Run the eval set: the real pipeline over locally labelled CV+JD pairs.

The pairs never enter the repository. A job post is a third party's page and a CV
is personal text, so `eval/cases`, `eval/gold`, `eval/reports` and
`eval/baseline.json` are ignored; only the `example-*` smoke pairs ship.

What is measured is judgment, not file handling: a case CV enters through the
same intake path as an upload, as a DOCX built in memory.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Final

from app.config import Settings
from app.container import Container, build_container
from app.db import Base, create_db_engine
from app.eval_cases import Case, docx_bytes, load_cases
from app.eval_metrics import (
    REFUSALS,
    CaseResult,
    EvalError,
    Outcome,
    match_requirements,
)
from app.eval_report import build_report, write_baseline, write_report
from app.modules.analysis import queries
from app.modules.analysis.enums import AnalysisStatus, Verdict
from app.modules.analysis.guard_types import numbers_in
from app.modules.analysis.prompts import load_prompt
from app.shared.errors import AppError
from app.shared.text import contains_quote

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
MATCH_PROMPT: Final = "match"


__all__ = [
    "Case",
    "EvalError",
    "REPO_ROOT",
    "build_eval_container",
    "eval_settings",
    "load_cases",
    "run_eval",
]

def _unsupported(payload: dict[str, Any], cv_text: str) -> int:
    """Re-checks the guard independently: every number in the output is in the CV."""
    known = numbers_in(cv_text)
    produced = [item.get("proposed_text") or "" for item in payload["suggestions"]]
    produced.append((payload.get("cover_note") or {}).get("text") or "")
    return sum(1 for text in produced if numbers_in(text) - known)


def _outcomes(
    payload: dict[str, Any], gold: list[tuple[str, str]], cv_text: str
) -> tuple[list[Outcome], int]:
    requirements = payload["requirements"]
    matches = {item["requirement_id"]: item for item in payload["matches"]}
    mapping = match_requirements([text for text, _ in gold], [row["text"] for row in requirements])
    outcomes: list[Outcome] = []
    for gold_index, (gold_text, gold_verdict) in enumerate(gold):
        extracted_index = mapping.get(gold_index)
        if extracted_index is None:
            # The pipeline never extracted it: no verdict is honest here.
            outcomes.append(Outcome(gold_text=gold_text, gold_verdict=gold_verdict))
            continue
        match = matches.get(requirements[extracted_index]["id"]) or {}
        quote = match.get("evidence_quote")
        # The rubric makes a quote mandatory for strong and partial, so a missing
        # or invented quote is ungrounded evidence whatever the verdict claims.
        # Containment is judged by the same rule the pipeline grounds with: the CV
        # is a PDF extraction, so a quote that reads as one space may sit across a
        # line break, and a curly quote in the CV may be a straight one in the
        # quote. Comparing raw strings marks those as invented.
        grounded = match.get("verdict") == Verdict.GAP or bool(
            quote and contains_quote(cv_text, quote)
        )
        outcomes.append(
            Outcome(
                gold_text=gold_text,
                gold_verdict=gold_verdict,
                verdict=match.get("verdict"),
                votes=dict(match.get("votes") or {}),
                evidence_quote=quote,
                grounded=grounded,
            )
        )
    return outcomes, len(mapping)


def build_eval_container(settings: Settings) -> Container:
    """A throwaway database: the eval never touches the real one."""
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    return build_container(settings, engine=engine)


def _refusal(case: Case, exc: AppError) -> CaseResult:
    """A refusal only passes when the case said to expect that exact code.

    `JD_NOT_FOUND` and `JD_MULTIPLE_JOBS` are the pipeline saying "this page is
    not one job post", which is a judgment about the prompt. Expecting a
    different code still counts as a miss, so a page cannot pass by accident.
    """
    return CaseResult(
        case_id=case.case_id,
        outcomes=[],
        extracted_total=0,
        extracted_matched=0,
        unsupported=0,
        tokens=0,
        latency_ms=0,
        expect=case.expect,
        actual=exc.code,
    )


def _run_case(container: Container, case: Case) -> CaseResult:
    cv = container.cvs.create(label=f"eval-{case.case_id}")
    version = container.cvs.add_version(
        cv["id"], file_name=f"{case.case_id}.docx", data=docx_bytes(case.cv_text)
    )
    job = container.jobs.create(title=case.title, company=case.company)
    snapshot = container.jobs.add_snapshot(
        job["id"], raw_text=case.jd_text, source_kind="page_paste"
    )
    try:
        payload = asyncio.run(
            container.analysis.run(cv_version_id=version["id"], snapshot_id=snapshot["id"])
        )
    except AppError as exc:
        # An unexpected refusal keeps the case id, because the finding is about
        # the prompt and the message must name the page that produced it.
        if case.expect in REFUSALS:
            return _refusal(case, exc)
        raise EvalError(f"{case.case_id} refused at {exc.code}: {exc}") from exc
    if case.expect in REFUSALS:
        raise EvalError(f"{case.case_id} was expected to refuse with {case.expect} but ran")
    if payload["status"] != AnalysisStatus.OK:
        raise EvalError(f"{case.case_id} did not finish: {payload['status']}")
    cv_text = container.cvs.parser_view(version["id"])["text"]
    outcomes, matched = _outcomes(payload, case.gold, cv_text)
    with container.session_factory() as session:
        calls = queries.calls_for_analysis(session, payload["id"])
    return CaseResult(
        case_id=case.case_id,
        outcomes=outcomes,
        extracted_total=len(payload["requirements"]),
        extracted_matched=matched,
        unsupported=_unsupported(payload, cv_text),
        tokens=sum(call.tokens_in + call.tokens_out for call in calls),
        latency_ms=sum(call.latency_ms for call in calls),
    )


def _run_all(settings: Settings, cases: list[Case]) -> tuple[list[CaseResult], list[str], int]:
    """One container for the whole set: a fresh one per case redoes every migration."""
    container = build_eval_container(settings)
    try:
        results: list[CaseResult] = []
        failures: list[str] = []
        for case in cases:
            try:
                results.append(_run_case(container, case))
            except EvalError as exc:
                failures.append(str(exc))
        return results, failures, max(1, container.matcher.runs)
    finally:
        container.engine.dispose()


def eval_settings(base: Settings | None) -> tuple[Settings, Path]:
    """A throwaway database per run, so an eval can never touch the real one.

    Everything else is inherited: the provider, the model and the prompts must be
    the ones the app actually uses, or the report means nothing.
    """
    scratch = Path(tempfile.mkdtemp(prefix="cvfit-eval-"))
    source = base or Settings(_env_file=None, prompts_dir=REPO_ROOT / "prompts")
    settings = source.model_copy(
        update={
            "database_url": f"sqlite:///{(scratch / 'eval.db').as_posix()}",
            "worker_enabled": False,
        }
    )
    return settings, scratch


def _read_baseline(baseline_path: Path | None) -> dict[str, Any] | None:
    if baseline_path is None or not Path(baseline_path).is_file():
        return None
    return json.loads(Path(baseline_path).read_text(encoding="utf-8"))


def run_eval(
    *,
    directory: Path,
    baseline_path: Path | None = None,
    limit: int | None = None,
    update_baseline: bool = False,
    report_base: Path | None = None,
    settings: Settings | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    """Run every case, write the report, return (report, json path, markdown path)."""
    cases = load_cases(directory, limit=limit)
    settings, scratch = eval_settings(settings)
    # Read before the cases run, not after. Editing a prompt mid-run used to
    # stamp the report with the new bundle while the verdicts came from the old
    # one, which is the single field a version comparison trusts.
    bundle = load_prompt(settings.prompts_dir, MATCH_PROMPT).ref.bundle
    try:
        results, failures, match_runs = _run_all(settings, cases)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    report = build_report(
        results=results,
        failures=failures,
        match_runs=match_runs,
        bundle=bundle,
        model=settings.llm_model,
        case_ids=[case.case_id for case in cases],
        baseline=_read_baseline(baseline_path),
    )
    json_path, md_path = write_report(report, directory=directory, report_base=report_base)
    if update_baseline and baseline_path is not None:
        write_baseline(baseline_path, report)
    return report, json_path, md_path
