"""Serve the built React app from the same process as the API.

Stage A used Swagger as the interim UI. This module is the whole difference:
hashed assets under ``/assets``, everything else the index document so client
routes survive a reload. Deep links must not swallow ``/api`` though, or a typo
in a fetch path would answer with HTML instead of the error envelope.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

ASSET_DIR = "assets"


def mount_ui(app: FastAPI, dist_dir: Path) -> bool:
    """Mount the built UI. Returns False when there is no build to serve.

    Absent dist is not an error: `pytest`, `alembic` and the CLI all build an
    app object without ever running `npm run build`.
    """
    index = dist_dir / "index.html"
    if not index.is_file():
        return False

    root = dist_dir.resolve()
    assets = dist_dir / ASSET_DIR
    if assets.is_dir():
        app.mount(f"/{ASSET_DIR}", StaticFiles(directory=assets), name="ui-assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def ui(path: str) -> FileResponse:
        # `/api/...` reaches here only when no router matched, so let the normal
        # 404 handler answer with JSON rather than an HTML page.
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(status_code=404, detail="Not Found")
        # `path` is request input: `..` must not escape the build directory.
        candidate = (root / path).resolve() if path else index
        if path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True
