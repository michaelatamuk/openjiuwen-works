"""The local FastAPI application.

The engine stays in-process; this module only wires HTTP onto it. Imports are lazy at the CLI edge
so `works --help` keeps working without the `server` extra.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
) -> FastAPI:
    trusted = frozenset(trusted_hosts or LOOPBACK)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
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

    @app.middleware("http")
    async def local_only(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        hostname = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
        if hostname not in trusted:
            return JSONResponse(
                status_code=403,
                content={
                    "ok": False,
                    "error": {"code": "forbidden", "message": "host not allowed"},
                },
            )
        origin = request.headers.get("origin")
        if origin:
            origin_host = urlsplit(origin).hostname or ""
            if origin_host not in trusted and origin_host != hostname:
                return JSONResponse(
                    status_code=403,
                    content={
                        "ok": False,
                        "error": {"code": "forbidden", "message": "origin not allowed"},
                    },
                )
        return await call_next(request)

    @app.exception_handler(WorksError)
    async def works_error(request: Request, exc: WorksError) -> JSONResponse:
        status = next(
            (code for error_type, code in ERROR_STATUS if isinstance(exc, error_type)), 500
        )
        return JSONResponse(status_code=status, content=_error_body(exc))

    for router in (
        health.router,
        admin.router,
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
