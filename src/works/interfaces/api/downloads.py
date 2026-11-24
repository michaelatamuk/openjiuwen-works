"""Resolve export and artifact downloads without touching the socket."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from works.config.paths import WorksPaths
from works.interfaces.api.presenters.tasks import _export, _run_index
from works.interfaces.api.static import _content_type


@dataclass(frozen=True)
class Download:
    content_type: str
    body: bytes
    filename: str
    inline: bool


def _download(target: Path, filename: str, *, inline: bool) -> Download:
    return Download(
        content_type=_content_type(target),
        body=target.read_bytes(),
        filename=filename,
        inline=inline,
    )


def find_export(paths: WorksPaths, task_id: str, kind: str) -> Download | None:
    found = _export(paths, task_id, kind)
    if found is None:
        return None
    target, filename = found
    return _download(target, filename, inline=False)


def find_artifact(paths: WorksPaths, task_id: str, name: str) -> Download | None:
    run_info = _run_index(paths).get(task_id)
    if run_info is None:
        return None
    root = (run_info[1] / "artifacts").resolve()
    target = (root / name).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return _download(target, target.name, inline=True)


def resolve_export(paths: WorksPaths, path: str) -> Download | None:
    rest = unquote(path.removeprefix("/api/tasks/"))
    task_id, separator, kind = rest.partition("/export/")
    if not separator or not task_id or not kind:
        return None
    return find_export(paths, task_id, kind)


def resolve_artifact(paths: WorksPaths, path: str) -> Download | None:
    rest = unquote(path.removeprefix("/api/tasks/"))
    task_id, separator, name = rest.partition("/artifacts/")
    if not separator or not task_id or not name:
        return None
    return find_artifact(paths, task_id, name)
