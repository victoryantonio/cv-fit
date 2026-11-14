"""Turning eval results into the report files. Rendering only, no judgment."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.eval_metrics import TARGETS, CaseResult, baseline_document, regressions, summarize


def build_report(
    *,
    results: list[CaseResult],
    failures: list[str],
    match_runs: int,
    bundle: str,
    model: str,
    case_ids: list[str],
    baseline: dict[str, Any] | None,
) -> dict[str, Any]:
    metrics = summarize(results, match_runs)
    failures += [
        f"{result.case_id} expected {result.expect} but got {result.actual}"
        for result in results
        if not result.satisfied
    ]
    problems = regressions(metrics, baseline, case_ids=tuple(case_ids)) + failures
    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "prompt_bundle": bundle,
        "match_runs": match_runs,
        "case_ids": sorted(case_ids),
        "metrics": metrics,
        "targets": TARGETS,
        "problems": problems,
        "cases": [result.as_dict(match_runs) for result in results],
    }
    report["passed"] = not problems
    return report


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"# Eval report {report['generated_at']}",
        "",
        f"Model `{report['model']}`, bundle `{report['prompt_bundle'][:8]}`, "
        f"{report['match_runs']} runs, {metrics['cases']} cases.",
        "",
        "| Metric | Value | Target |",
        "| --- | --- | --- |",
        f"| Agreement | {metrics['agreement']:.1%} | {TARGETS['agreement']:.0%} |",
        f"| Stability | {metrics['stability']:.1%} | {TARGETS['stability']:.0%} |",
        f"| Structuring | {metrics['structuring_accuracy']:.1%} | "
        f"{TARGETS['structuring_accuracy']:.0%} |",
        f"| Ungrounded quotes | {metrics['ungrounded']} | 0 |",
        f"| Unsupported facts | {metrics['unsupported']} | 0 |",
        f"| Refusals correct | {metrics['refusals_correct']}/{metrics['refusals']} | all of them |",
        f"| Tokens | {metrics['tokens']} | within budget |",
        f"| Latency P50 / P95 | {metrics['latency_p50_ms']} / "
        f"{metrics['latency_p95_ms']} ms | tune |",
        "",
        "| Case | Expect | Got | Requirements | Agree | Extracted | Matched |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["cases"]:
        agreed = sum(1 for item in case["requirements"] if item["agree"])
        lines.append(
            f"| {case['case_id']} | {case['expect']} | {case['actual']} | "
            f"{len(case['requirements'])} | {agreed} | "
            f"{case['extracted_total']} | {case['extracted_matched']} |"
        )
    lines.append("")
    if report["problems"]:
        lines.append("## Blocking problems")
        lines.extend(f"- {problem}" for problem in report["problems"])
    else:
        lines.append("No blocking problems. This run is a valid baseline candidate.")
    return "\n".join(lines) + "\n"


def write_report(
    report: dict[str, Any], *, directory: Path, report_base: Path | None
) -> tuple[Path, Path]:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = report_base or (directory / "reports" / f"{stamp}-{report['prompt_bundle'][:8]}")
    base.parent.mkdir(parents=True, exist_ok=True)
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def write_baseline(path: Path, report: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    document = baseline_document(report)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
