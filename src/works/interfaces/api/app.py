"""The local FastAPI application.

The engine stays in-process; this module only wires HTTP onto it. Imports are lazy at the CLI edge
so `works --help` keeps working without the `server` extra.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from works.application.observability.tracing import configure_tracing
from works.config.paths import WorksPaths
from works.domain.errors import (
    AuthError,
    ConfigError,
    ConflictError,
    HarnessError,
    NotFoundError,
    PolicyError,
    ReadOnlyError,
    StateError,
    UnavailableError,
    WorksError,
)
from works.interfaces.api.context import RequestContextMiddleware
from works.interfaces.api.guard import LocalOnlyMiddleware, ReadAuthMiddleware
from works.interfaces.api.http_tracing import TracingMiddleware
from works.interfaces.api.idempotency import IdempotencyMiddleware
from works.interfaces.api.limits import BodyLimitMiddleware
from works.interfaces.api.ratelimit import RateLimitMiddleware
from works.interfaces.api.routes import (
    actions,
    admin,
    ask,
    downloads,
    events,
    health,
    jobs,
    maps,
    observability,
    ops,
    pair,
    readiness,
    runs,
    session,
    settings,
    sources,
    tasks,
)
from works.interfaces.api.wiring import AppState, build_state

VERSION = "0.0.1"
DIST = Path(__file__).resolve().parents[1] / "ui" / "static" / "dist"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
MAX_BODY = int(os.environ.get("WORKS_MAX_BODY_BYTES", str(4 * 1024 * 1024)))
ERROR_STATUS: tuple[tuple[type[WorksError], int], ...] = (
    (ReadOnlyError, 403),
    (AuthError, 401),
    (PolicyError, 403),
    (NotFoundError, 404),
    (StateError, 409),
    (ConflictError, 409),
    (HarnessError, 502),
    (UnavailableError, 503),
    (ConfigError, 400),
    (WorksError, 500),
)


def _error_body(exc: WorksError) -> dict[str, object]:
    return {"ok": False, "error": {"code": exc.code, "message": str(exc)}}


def create_app(
    paths: WorksPaths | Path | None = None,
    *,
    writable: bool = False,
    trusted_hosts: tuple[str, ...] | None = None,
    bootstrap_token: str | None = None,
    state: AppState | None = None,
    max_body_bytes: int = MAX_BODY,
    require_auth: bool = False,
    rate_limit: bool = True,
) -> FastAPI:
    trusted = frozenset(trusted_hosts or LOOPBACK)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_tracing()
        current = state or build_state(paths, writable=writable, bootstrap_token=bootstrap_token)
        application.state.works = current
        current.live.start()
        try:
            yield
        finally:
            current.live.stop()
            current.jobs.shutdown()

    app = FastAPI(
        title="openJiuwen Works",
        version=VERSION,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    # `add_middleware` is innermost-first. Outer order:
    # request id -> body limit -> rate limit -> host -> read auth -> idempotency.
    app.add_middleware(IdempotencyMiddleware)
    app.add_middleware(
        ReadAuthMiddleware,
        require=require_auth,
        authorize=lambda request: bool(app.state.works.security.is_authenticated(request)),
    )
    app.add_middleware(LocalOnlyMiddleware, trusted=trusted)
    app.add_middleware(RateLimitMiddleware, enabled=rate_limit)
    app.add_middleware(BodyLimitMiddleware, max_bytes=max_body_bytes)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(TracingMiddleware)

    @app.exception_handler(WorksError)
    async def works_error(request: Request, exc: WorksError) -> JSONResponse:
        status = next(
            (code for error_type, code in ERROR_STATUS if isinstance(exc, error_type)), 500
        )
        headers = {"Retry-After": "5"} if status == 503 else None
        return JSONResponse(status_code=status, content=_error_body(exc), headers=headers)

    for router in (
        health.router,
        admin.router,
        pair.router,
        session.router,
        actions.router,
        runs.router,
        events.router,
        ask.router,
        readiness.router,
        sources.router,
        settings.router,
        tasks.router,
        jobs.router,
        maps.router,
        observability.router,
        ops.router,
        downloads.router,
    ):
        app.include_router(router, prefix="/api/v1")

    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> Response:
            target = DIST / "index.html"
            if not target.is_file():
                return JSONResponse(
                    status_code=404,
                    content={
                        "ok": False,
                        "error": {
                            "code": "not_found",
                            "message": "UI bundle missing; run `npm --prefix web run build`",
                        },
                    },
                )
            return FileResponse(target)

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            if path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={
                        "ok": False,
                        "error": {"code": "not_found", "message": "unknown endpoint"},
                    },
                )
            root = DIST.resolve()
            target = (DIST / path).resolve()
            if path and root in target.parents and target.is_file():
                return FileResponse(target)
            index_file = DIST / "index.html"
            if index_file.is_file():
                return FileResponse(index_file)
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": {
                        "code": "not_found",
                        "message": "UI bundle missing; run `npm --prefix web run build`",
                    },
                },
            )

    return app
