"""Read routes: JSON payloads for the queue, task, metrics and settings."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.observability.metrics import collect
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.interfaces.api.presenters.tasks import (
    _run_summaries,
    _task_detail,
    _tasks,
    detector_map,
    product_map,
)

Result = tuple[HTTPStatus, dict[str, Any]]


def health(paths: WorksPaths, *, writable: bool) -> Result:
    from works.application.assistant.chat import availability
    from works.application.settings import builder_health, load_builder_settings

    try:
        settings = load_builder_settings(paths)
    except ConfigError:
        settings = None
    return (
        HTTPStatus.OK,
        {
            "ok": True,
            "readonly": not writable,
            "write": writable,
            "root": str(paths.root),
            "version": "0.0.1",
            "ai": availability(),
            "builder": builder_health(paths, settings),
        },
    )


def products(paths: WorksPaths) -> Result:
    return HTTPStatus.OK, {"ok": True, **product_map(paths)}


def detectors(paths: WorksPaths, *, refresh: bool) -> Result:
    return HTTPStatus.OK, {"ok": True, **detector_map(paths, refresh=refresh)}


def tasks(paths: WorksPaths, *, limit: int) -> Result:
    return HTTPStatus.OK, {"tasks": _tasks(Queue(paths), limit)}


def runs(paths: WorksPaths, task_id: str) -> Result:
    return HTTPStatus.OK, {"runs": _run_summaries(paths, task_id)}


def detail(paths: WorksPaths, task_id: str) -> Result:
    return HTTPStatus.OK, _task_detail(Queue(paths), paths, task_id)


def metrics(paths: WorksPaths) -> Result:
    queue = Queue(paths)
    return (
        HTTPStatus.OK,
        {"metrics": collect(queue, Ledger(paths.ledger)).model_dump(mode="json")},
    )


def ledger(paths: WorksPaths) -> Result:
    rows = Ledger(paths.ledger).rows()
    return HTTPStatus.OK, {"rows": [row.model_dump(mode="json") for row in rows[-200:]]}
