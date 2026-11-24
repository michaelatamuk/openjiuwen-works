"""Run artifacts and downloadable exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from works.config.paths import WorksPaths
from works.interfaces.api.presenters.tasks.files import _run_index


def _artifact_kind(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        return "image"
    if suffix in {".mp4", ".webm", ".mov"}:
        return "video"
    if suffix in {".log", ".txt", ".md"}:
        return "log"
    if suffix in {".json", ".trace"}:
        return "trace"
    return "file"


def _artifact_list(
    run_dir: Path | None, task_id: str, evidence: dict[str, Any] | None
) -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for artifact in (evidence or {}).get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        relative = str(artifact.get("path") or "").removeprefix("artifacts/")
        if not relative:
            continue
        items[relative] = {
            "path": relative,
            "name": Path(relative).name,
            "kind": str(artifact.get("kind") or _artifact_kind(relative)),
            "sha256": str(artifact.get("sha256") or ""),
            "url": f"/api/tasks/{quote(task_id)}/artifacts/"
            + "/".join(quote(part) for part in relative.split("/")),
        }
    root = (run_dir / "artifacts") if run_dir is not None else None
    if root is not None and root.exists():
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if relative in items:
                continue
            items[relative] = {
                "path": relative,
                "name": path.name,
                "kind": _artifact_kind(relative),
                "sha256": "",
                "size": path.stat().st_size,
                "url": f"/api/tasks/{quote(task_id)}/artifacts/"
                + "/".join(quote(part) for part in relative.split("/")),
            }
    return sorted(items.values(), key=lambda item: item["path"])


def _export(paths: WorksPaths, task_id: str, kind: str) -> tuple[Path, str] | None:
    run_info = _run_index(paths).get(task_id)
    if run_info is None:
        return None
    run_dir = run_info[1]
    names = {
        "evidence.md": run_dir / "evidence.md",
        "evidence.json": run_dir / "evidence.json",
        "run.json": run_dir / "run.json",
        "release.json": run_dir / "release.json",
        "delivery.json": run_dir / "delivery.json",
        "deployment.json": run_dir / "deployment.json",
        "confirmation.json": run_dir / "confirmation.json",
    }
    target = names.get(kind)
    if target is None or not target.is_file():
        return None
    return target, f"{task_id}-{kind}"
