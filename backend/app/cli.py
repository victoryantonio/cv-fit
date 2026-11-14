"""Stage A interim UI. Every subcommand prints JSON so it can be piped."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from app.cli_intake import (
    cv_add,
    cv_preview,
    cv_show,
    job_add,
    job_list,
    job_paste,
    job_show,
    job_status,
    job_structure,
    job_sync_alerts,
    print_json,
)
from app.cli_parser import build_parser
from app.container import Container, build_container
from app.eval_cli import EvalError, run_eval
from app.modules.analysis.enums import TaskStatus
from app.modules.analysis.export import render_markdown
from app.shared.errors import AppError

#: A task in one of these states will not move again without an explicit retry.
TERMINAL: frozenset[str] = frozenset({TaskStatus.OK, TaskStatus.FAILED, TaskStatus.CANCELLED})



def _health(container: Container) -> int:
    report = asyncio.run(container.health.check(refresh=True))
    print_json(report.as_dict())
    return 0


def _export_schemas(container: Container) -> int:
    from app.modules.analysis.schemas import write_schema_snapshots

    paths = write_schema_snapshots(container.settings.prompts_dir)
    print_json({"written": [str(path) for path in paths]})
    return 0


def _openapi(container: Container, args: argparse.Namespace) -> int:
    """Dump the spec to a file so the TS client can be generated offline.

    Committed rather than fetched from a running server: `npm run check:api`
    then works on a fresh clone, and the pytest contract test can compare the
    file against `create_app().openapi()` without binding a port.
    """
    from app.main import create_app

    spec = create_app(container).openapi()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Sorted and indented: the file is diffed, so ordering must be stable.
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print_json({"written": str(out), "paths": len(spec["paths"])})
    return 0


def _drain(container: Container) -> None:
    """Run the queue to the end. The CLI is its own worker for one command."""
    while asyncio.run(container.worker.run_once()) is not None:
        continue


def _analyze(container: Container, args: argparse.Namespace) -> int:
    queued = container.tasks.enqueue(
        cv_version_id=args.cv_version,
        snapshot_id=args.snapshot,
        force=args.force,
        override_budget=args.override_budget,
    )
    if queued.cache_hit:
        result = container.analysis.get(str(queued.analysis_id))
        print_json(
            {
                "analysis_id": result["id"],
                "status": result["status"],
                "cache_hit": True,
                "cache_key": result["cache_key"],
                "model": result["model"],
                "match_runs": result["match_runs"],
                "summary": result["summary"],
            }
        )
        return 0
    _drain(container)
    task = container.tasks.get(str(queued.task_id))
    if task["status"] != TaskStatus.OK:
        print_json({"task_id": task["id"], "status": task["status"], "error": task["error_code"]})
        return 1
    result = container.analysis.get(str(task["analysis_id"]))
    print_json(
        {
            "task_id": task["id"],
            "analysis_id": result["id"],
            "status": result["status"],
            "cache_hit": False,
            "cache_key": result["cache_key"],
            "model": result["model"],
            "match_runs": result["match_runs"],
            "summary": result["summary"],
        }
    )
    return 0


def _packet(container: Container, args: argparse.Namespace) -> int:
    if args.md:
        payload = container.analysis.get(args.analysis_id)
        Path(args.md).write_text(render_markdown(payload), encoding="utf-8")
        print_json({"written": str(Path(args.md).resolve())})
        return 0
    if args.suggestions:
        payload = container.analysis.get(args.analysis_id, include_rejected=True)
        print_json(
            {
                "suggestions": payload["suggestions"],
                "rejected": payload.get("suggestions_rejected", []),
                "provenance": payload["suggestion_provenance"],
            }
        )
        return 0
    payload = container.analysis.get(args.analysis_id)
    print_json(payload["summary"] if args.summary else payload)
    return 0


def _task_list(container: Container, args: argparse.Namespace) -> int:
    print_json(container.tasks.recent(limit=args.limit))
    return 0


def _task_watch(container: Container, args: argparse.Namespace) -> int:
    """Follow one task. Prints a line per change, then the task as JSON."""
    interval = args.interval or container.settings.worker_poll_seconds
    seen: set[str] = set()
    while True:
        task = container.tasks.get(args.task_id)
        mark = f"{task['status']}:{task['current_step']}"
        if mark not in seen:
            seen.add(mark)
            print(f"{task['status']:<10} {task['current_step'] or '-'}", file=sys.stderr)
        if task["status"] in TERMINAL:
            print_json(task)
            return 0 if task["status"] == TaskStatus.OK else 1
        time.sleep(interval)


def _eval(container: Container, args: argparse.Namespace) -> int:
    directory = Path(args.dir)
    try:
        report, json_path, md_path = run_eval(
            directory=directory,
            baseline_path=Path(args.baseline) if args.baseline else directory / "baseline.json",
            limit=args.limit,
            update_baseline=args.update_baseline,
            settings=container.settings,
        )
    except EvalError as exc:
        # A broken eval set is my mistake, not a crash: say which file and stop.
        print_json({"error": "EVAL_SET_INVALID", "message": str(exc)})
        return 1
    print_json(
        {
            "report": str(json_path),
            "markdown": str(md_path),
            "passed": report["passed"],
            "metrics": report["metrics"],
            "problems": report["problems"],
        }
    )
    return 0 if report["passed"] else 1


def _dispatch(container: Container, args: argparse.Namespace) -> int:
    if args.command == "health":
        return _health(container)
    if args.command == "export-schemas":
        return _export_schemas(container)
    if args.command == "openapi":
        return _openapi(container, args)
    if args.command == "cv":
        handlers = {
            "add": cv_add,
            "show": cv_show,
            "preview": cv_preview,
        }
        return handlers[args.cv_command](container, args)
    if args.command == "job":
        handlers = {
            "add": job_add,
            "paste": job_paste,
            "list": job_list,
            "show": job_show,
            "sync-alerts": job_sync_alerts,
            "structure": job_structure,
            "status": job_status,
        }
        return handlers[args.job_command](container, args)
    if args.command == "analyze":
        return _analyze(container, args)
    if args.command == "packet":
        return _packet(container, args)
    if args.command == "task":
        handlers = {"list": _task_list, "watch": _task_watch}
        return handlers[args.task_command](container, args)
    if args.command == "eval":
        return _eval(container, args)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    container = build_container()
    try:
        return _dispatch(container, args)
    except AppError as exc:
        print_json(exc.envelope(None))
        return 1


if __name__ == "__main__":
    sys.exit(main())


