"""Document parsing in a short-lived subprocess (see `parser_worker`).

`SubprocessParser` is the only `DocumentParser` implementation used by the app:
a malformed document must not be able to block the API process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Final

from app.modules.cvs.parser import DocumentParseError, ParsedCv

BACKEND_DIR: Final = Path(__file__).resolve().parents[3]
WORKER_MODULE: Final = "app.modules.cvs.parser_worker"
DEFAULT_TIMEOUT_SECONDS: Final = 30.0


class SubprocessParser:
    """Runs the parser out of process so a hang or a crash cannot take the API down."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        python_executable: str | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.python_executable = python_executable or sys.executable

    def _environment(self) -> dict[str, str]:
        # The app package is not installed in the venv, so the child needs the
        # backend directory on its path.
        env = dict(os.environ)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(BACKEND_DIR) + (os.pathsep + existing if existing else "")
        return env

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        suffix = Path(file_name).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            path = Path(handle.name)
        try:
            request = json.dumps({"file_path": str(path), "file_name": file_name})
            try:
                completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                    [self.python_executable, "-m", WORKER_MODULE],
                    input=request,
                    capture_output=True,
                    text=True,
                    # The worker writes UTF-8; decoding with the locale codepage
                    # would mangle or reject any CV that is not plain ASCII.
                    encoding="utf-8",
                    timeout=self.timeout_seconds,
                    env=self._environment(),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise DocumentParseError("parser timed out") from exc
        finally:
            path.unlink(missing_ok=True)

        if not completed.stdout.strip():
            raise DocumentParseError("parser produced no output")
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise DocumentParseError("parser produced invalid JSON") from exc
        if not payload.get("ok"):
            raise DocumentParseError(str(payload.get("detail") or payload.get("reason")))
        return ParsedCv(**payload["result"])
