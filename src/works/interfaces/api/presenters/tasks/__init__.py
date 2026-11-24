"""Task presenters: run files, maps, artifacts and the task detail."""

from __future__ import annotations

from works.interfaces.api.presenters.tasks.artifacts import (
    _artifact_kind,
    _artifact_list,
    _export,
)
from works.interfaces.api.presenters.tasks.detail import (
    _run_summaries,
    _task_detail,
    _task_summary,
    _tasks,
)
from works.interfaces.api.presenters.tasks.files import (
    _latest,
    _read_json,
    _run_index,
    feature_map,
    readiness,
)
from works.interfaces.api.presenters.tasks.maps import detector_map, product_map

__all__ = [
    "_artifact_kind",
    "_artifact_list",
    "_export",
    "_latest",
    "_read_json",
    "_run_index",
    "_run_summaries",
    "_task_detail",
    "_task_summary",
    "_tasks",
    "detector_map",
    "feature_map",
    "product_map",
    "readiness",
]
