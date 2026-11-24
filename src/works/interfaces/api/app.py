"""The local FastAPI application.

The engine stays in-process; this module only wires HTTP onto it. Imports are lazy at the CLI edge
so `works --help` keeps working without the `server` extra.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from works.config.paths import WorksPaths
from works.interfaces.api.routes import health
from works.interfaces.api.wiring import build_state

VERSION = "0.0.1"


def create_app(paths: WorksPaths | None = None, *, writable: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.works = build_state(paths, writable=writable)
        yield

    app = FastAPI(
        title="openJiuwen Works",
        version=VERSION,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url=None,
        redoc_url=None,
    )
    app.include_router(health.router, prefix="/api/v1")
    return app
