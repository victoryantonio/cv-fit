"""Subprocess entrypoint for parsing: `python -m app.modules.cvs.parser_worker`.

A CV parser that hangs or dies takes down the whole API process if it runs
in-process, so it runs here behind a timeout. Reads JSON on stdin, writes JSON on
stdout. Never logs document text; on failure it reports the exception type only.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

from app.modules.cvs.parser import DocumentParseError, parse_document


def run(request: dict[str, Any]) -> dict[str, Any]:
    file_path = Path(str(request["file_path"]))
    file_name = str(request["file_name"])
    try:
        parsed = parse_document(file_path.read_bytes(), file_name=file_name)
    except DocumentParseError as exc:
        return {"ok": False, "reason": "parse_error", "detail": str(exc)}
    except OSError as exc:
        return {"ok": False, "reason": "io_error", "detail": type(exc).__name__}
    except Exception as exc:  # noqa: BLE001 - the parent decides what a crash means
        return {"ok": False, "reason": "crash", "detail": type(exc).__name__}
    return {"ok": True, "result": parsed.as_dict()}


def main() -> int:
    # Pipes default to the ANSI codepage on Windows, and one bullet or smart
    # quote in a CV is enough to make that encoding fail mid-write, which the
    # parent then reads as "no output". The protocol is UTF-8 on both ends.
    if isinstance(sys.stdin, io.TextIOWrapper):
        sys.stdin.reconfigure(encoding="utf-8")
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    request = json.loads(sys.stdin.read() or "{}")
    response = run(request)
    sys.stdout.write(json.dumps(response, ensure_ascii=False))
    sys.stdout.flush()
    return 0 if response["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
