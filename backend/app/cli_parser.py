"""Command tree for the Stage A CLI.

Separate from `cli.py` because arguments and behaviour change for different
reasons: a new flag touches this file only, a new side effect touches that one.
"""

from __future__ import annotations

import argparse

#: Choices for `job paste --source-kind`. A URL fetch is recorded, never performed here.
SOURCE_KINDS: tuple[str, ...] = ("page_paste", "text_paste", "url_fetch")


def _cv(subparsers: argparse._SubParsersAction) -> None:
    cv = subparsers.add_parser("cv", help="CV intake and preview")
    cv_sub = cv.add_subparsers(dest="cv_command", required=True)

    add = cv_sub.add_parser("add", help="Create a CV and attach its first file")
    add.add_argument("--label", required=True, help="Label shown in the UI (<= 60 chars)")
    add.add_argument("--file", required=True, help="Path to a PDF or DOCX file")
    add.add_argument("--target-role", default=None, help="Optional target role")
    add.add_argument("--note", default=None, help="Optional note for this version")

    show = cv_sub.add_parser("show", help="List CVs, or show one CV's impact counts")
    show.add_argument("id", nargs="?", default=None, help="CV id")

    preview = cv_sub.add_parser("preview", help="Print the redacted text sent to an LLM")
    preview.add_argument("id", help="CV version id")


def _job_filters(command: argparse.ArgumentParser) -> None:
    """`list` and `show` accept the same filters, so they must accept them alike."""
    command.add_argument("--status", default=None, help="Filter the list by status")
    command.add_argument(
        "--filtered",
        action="store_true",
        default=None,
        help="Only jobs the pre-filter rejected",
    )


def _job(subparsers: argparse._SubParsersAction) -> None:
    job = subparsers.add_parser("job", help="Job intake, JD snapshots and extraction")
    job_sub = job.add_subparsers(dest="job_command", required=True)

    add = job_sub.add_parser("add", help="Create a manually entered job")
    add.add_argument("--title", required=True)
    add.add_argument("--company", default=None)
    add.add_argument("--location", default=None)
    add.add_argument("--url", default=None)

    paste = job_sub.add_parser("paste", help="Store a JD snapshot for a job")
    paste.add_argument("id", help="Job id")
    paste.add_argument("--file", required=True, help="UTF-8 text file, or - for stdin")
    paste.add_argument("--source-kind", default="page_paste", choices=SOURCE_KINDS)

    show = job_sub.add_parser("show", help="List jobs, or show one job with its snapshots")
    show.add_argument("id", nargs="?", default=None, help="Job id")
    _job_filters(show)
    _job_filters(job_sub.add_parser("list", help="List jobs, newest first"))

    sync = job_sub.add_parser("sync-alerts", help="Pull new jobs from alert emails")
    sync.add_argument("--limit", type=int, default=25, help="Message limit (1-50)")
    sync.add_argument("--since", default=None, help="ISO 8601 lower bound")

    structure = job_sub.add_parser("structure", help="Run S1 extraction on a snapshot")
    structure.add_argument("snapshot_id", help="JD snapshot id")

    status = job_sub.add_parser("status", help="Move a job through the triage states")
    status.add_argument("id", help="Job id")
    status.add_argument("--status", default=None)
    status.add_argument("--outcome", default=None)


def _analyze(subparsers: argparse._SubParsersAction) -> None:
    analyze = subparsers.add_parser("analyze", help="Run the full pipeline for one CV and JD")
    analyze.add_argument("--cv-version", required=True, help="CV version id")
    analyze.add_argument("--snapshot", required=True, help="JD snapshot id")
    analyze.add_argument("--force", action="store_true", help="Ignore a cached result")
    analyze.add_argument(
        "--override-budget", action="store_true", help="Run despite the monthly token cap"
    )


def _task(subparsers: argparse._SubParsersAction) -> None:
    task = subparsers.add_parser("task", help="Inspect the analysis queue")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    listed = task_sub.add_parser("list", help="Recent tasks, newest first")
    listed.add_argument("--limit", type=int, default=20)
    watch = task_sub.add_parser("watch", help="Follow one task until it stops moving")
    watch.add_argument("task_id")
    watch.add_argument("--interval", type=float, default=None, help="Seconds between polls")


def _eval(subparsers: argparse._SubParsersAction) -> None:
    eval_parser = subparsers.add_parser("eval", help="Run the eval set and write a report")
    eval_parser.add_argument("--dir", default="eval", help="Directory holding cases/ and gold/")
    eval_parser.add_argument("--baseline", default=None, help="Baseline JSON to compare against")
    eval_parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases")
    eval_parser.add_argument(
        "--update-baseline", action="store_true", help="Accept this run as the baseline"
    )


def _packet(subparsers: argparse._SubParsersAction) -> None:
    packet = subparsers.add_parser("packet", help="Print a stored analysis packet")
    packet.add_argument("--analysis-id", required=True, help="Analysis id")
    packet.add_argument("--summary", action="store_true", help="Print the fit summary only")
    packet.add_argument(
        "--suggestions", action="store_true", help="Print suggestions and their guard verdicts"
    )
    packet.add_argument("--md", default=None, help="Write the packet as Markdown to this path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="CV-Job Fit Analyzer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Print the health report as JSON")
    subparsers.add_parser("export-schemas", help="Write JSON Schema snapshots")

    openapi = subparsers.add_parser("openapi", help="Write the schema the UI client is built from")
    openapi.add_argument("--out", default="frontend/openapi.json", help="Output path")

    _cv(subparsers)
    _job(subparsers)
    _analyze(subparsers)
    _task(subparsers)
    _eval(subparsers)
    _packet(subparsers)
    return parser
