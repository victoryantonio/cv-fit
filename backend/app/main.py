"""FastAPI application: middleware, the single error envelope, and routers."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from app.container import Container, build_container
from app.modules.analysis.api import router as analysis_router
from app.modules.cvs.api import router as cvs_router
from app.modules.jobs.api import router as jobs_router
from app.modules.platform.api import router as platform_router
from app.modules.platform.static_ui import mount_ui
from app.shared.errors import AppError
from app.shared.logging import configure_logging, get_logger, request_id_var

logger = get_logger(__name__)

_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _request_id(request: Request) -> str | None:
    """The id lives on the scope as well as the contextvar.

    The catch-all handler runs outside this app's middleware, where the
    contextvar has already been reset.
    """
    scoped: str | None = getattr(request.state, "request_id", None)
    return scoped or request_id_var.get()


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    configure_logging(container.settings.log_level)
    app = FastAPI(title="CV-Job Fit Analyzer", version="0.1.0", lifespan=_lifespan)
    # Set before the lifespan runs: startup reads the container back off the app.
    app.state.container = container
    _install_middleware(app, container)
    _install_handlers(app)
    app.include_router(platform_router)
    app.include_router(cvs_router)
    app.include_router(jobs_router)
    app.include_router(analysis_router)
    # Last, so the UI catch-all never shadows an API route.
    mount_ui(app, container.settings.ui_dist_dir)
    return app


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container: Container = app.state.container
    stop = asyncio.Event()
    runner: asyncio.Task[None] | None = None
    if container.settings.worker_enabled:
        runner = asyncio.create_task(container.worker.run_forever(stop))
    try:
        yield
    finally:
        stop.set()
        if runner is not None:
            # Let the worker land its current task: a cancelled task is
            # released back to the queue, never left running.
            runner.cancel()
            with suppress(asyncio.CancelledError):
                await runner
        container.engine.dispose()


def _install_middleware(app: FastAPI, container: Container) -> None:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=container.settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code or 500,
            content=exc.envelope(_request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = {
            "errors": [
                {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
                for err in exc.errors()
            ]
        }
        error = AppError("VALIDATION_ERROR", "Request validation failed.", details)
        return JSONResponse(
            status_code=error.status_code or 422,
            content=error.envelope(_request_id(request)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "INTERNAL_ERROR")
        error = AppError(code, str(exc.detail), status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=error.envelope(_request_id(request)),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the type only: tracebacks can contain CV or JD text.
        logger.error("unhandled_exception", extra={"outcome": type(exc).__name__})
        error = AppError("INTERNAL_ERROR", "An unexpected error occurred.", status_code=500)
        return JSONResponse(status_code=500, content=error.envelope(_request_id(request)))


app = create_app()
