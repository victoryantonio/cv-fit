"""The cv and job subcommands: intake and inspection, one JSON blob each.

Split out of `cli` so the dispatch table there reads as a list of commands
rather than as the body of all of them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from app.container import Container


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def cv_add(container: Container, args: argparse.Namespace) -> int:
    path = Path(args.file)
    created = container.cvs.create(label=args.label, target_role=args.target_role)
    version = container.cvs.add_version(
        created["id"],
        file_name=path.name,
        data=path.read_bytes(),
        note=args.note,
    )
    print_json(
        {
            "cv": created,
            "version_id": version["id"],
            "version_no": version["version_no"],
            "warnings": version["warnings"],
            "sections": version["sections"],
            "redacted_chars": version["redacted_chars"],
            "redaction": version["redaction"],
        }
    )
    return 0


def cv_show(container: Container, args: argparse.Namespace) -> int:
    if args.id is None:
        print_json(container.cvs.list_all())
        return 0
    print_json(container.cvs.impact(args.id))
    return 0


def cv_preview(container: Container, args: argparse.Namespace) -> int:
    print_json(container.cvs.parser_view(args.id))
    return 0


def job_add(container: Container, args: argparse.Namespace) -> int:
    print_json(
        container.jobs.create(
            title=args.title,
            company=args.company,
            url=args.url,
            location=args.location,
        )
    )
    return 0


def job_paste(container: Container, args: argparse.Namespace) -> int:
    text = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    print_json(container.jobs.add_snapshot(args.id, raw_text=text, source_kind=args.source_kind))
    return 0


def job_list(container: Container, args: argparse.Namespace) -> int:
    print_json(container.jobs.list(status=args.status, filtered=args.filtered))
    return 0


def job_show(container: Container, args: argparse.Namespace) -> int:
    if args.id is None:
        return job_list(container, args)
    print_json(container.jobs.get(args.id))
    return 0


def job_sync_alerts(container: Container, args: argparse.Namespace) -> int:
    since = datetime.fromisoformat(args.since) if args.since else None
    print_json(asyncio.run(container.jobs.sync_alerts(since=since, limit=args.limit)))
    return 0


def job_structure(container: Container, args: argparse.Namespace) -> int:
    snapshot = container.jobs.snapshot(args.snapshot_id)
    result = asyncio.run(
        container.jd_structurer.run(
            snapshot_id=snapshot["id"],
            raw_text=snapshot["raw_text"],
            text_sha256=snapshot["text_sha256"],
        )
    )
    print_json(result.as_dict())
    return 0


def job_status(container: Container, args: argparse.Namespace) -> int:
    print_json(container.jobs.update(args.id, status=args.status, outcome=args.outcome))
    return 0





