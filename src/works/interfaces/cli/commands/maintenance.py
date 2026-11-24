"""Backup and restore a home without exporting credentials or disposable worktrees."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

from works.config.paths import WorksPaths
from works.domain.errors import ConfigError, NotFoundError
from works.interfaces.cli.commands.common import _emit, _paths

ARCHIVE_DIRS = ("queue", "runs", "flows")
ARCHIVE_FILES = ("ledger.jsonl",)
WORKSPACE_FILES = (
    "settings.json",
    "products.yaml",
    "detectors.yaml",
    "readiness.yaml",
    "alerts.json",
)


def _workspace_files(paths: WorksPaths) -> list[Path]:
    root = paths.root / ".works"
    return [root / name for name in WORKSPACE_FILES if (root / name).is_file()]


def _has_data(paths: WorksPaths) -> bool:
    return (
        any((paths.queue).glob("*/events.jsonl"))
        or any((paths.runs).glob("*/run.json"))
        or paths.ledger.is_file()
    )


def cmd_backup(args: Any) -> int:
    paths = _paths(args)
    target = Path(args.out).expanduser()
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with tarfile.open(target, "w:gz") as archive:
        for name in ARCHIVE_DIRS:
            source = paths.root / name
            if source.is_dir():
                for item in sorted(source.rglob("*")):
                    if item.is_file():
                        archive.add(item, arcname=f"{name}/{item.relative_to(source).as_posix()}")
                        count += 1
        for name in ARCHIVE_FILES:
            source = paths.root / name
            if source.is_file():
                archive.add(source, arcname=name)
                count += 1
        for source in _workspace_files(paths):
            archive.add(source, arcname=f".works/{source.name}")
            count += 1
    payload = {"ok": True, "path": str(target), "files": count, "bytes": target.stat().st_size}
    if args.json:
        _emit(payload)
    else:
        print(f"backup {target} ({count} files, {payload['bytes']} bytes)")
    return 0


def cmd_restore(args: Any) -> int:
    paths = _paths(args)
    source = Path(args.source).expanduser()
    if not source.is_file():
        raise NotFoundError(f"backup not found: {source}")
    if _has_data(paths) and not args.force:
        raise ConfigError("the home already has data; pass --force to replace queue/runs/flows")
    with tempfile.TemporaryDirectory(prefix="works-restore-") as raw:
        staging = Path(raw)
        with tarfile.open(source, "r:gz") as archive:
            archive.extractall(staging, filter="data")
        for name in ARCHIVE_DIRS:
            candidate = staging / name
            if not candidate.is_dir():
                continue
            destination = paths.root / name
            if destination.exists():
                shutil.rmtree(destination)
            shutil.move(str(candidate), str(destination))
        for name in ARCHIVE_FILES:
            candidate = staging / name
            if candidate.is_file():
                shutil.copy2(candidate, paths.root / name)
        workspace = staging / ".works"
        if workspace.is_dir():
            (paths.root / ".works").mkdir(parents=True, exist_ok=True)
            for item in workspace.iterdir():
                if item.is_file() and item.name in WORKSPACE_FILES:
                    shutil.copy2(item, paths.root / ".works" / item.name)
    paths.ensure()
    payload = {"ok": True, "source": str(source), "root": str(paths.root)}
    if args.json:
        _emit(payload)
    else:
        print(f"restored {source} into {paths.root}")
    return 0


def cmd_prune_jobs(args: Any) -> int:
    paths = _paths(args)
    directory = paths.state / "jobs"
    cutoff = time.time() - float(args.days) * 86_400
    archive = paths.state / "jobs-archive.jsonl"
    removed = 0
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("status") not in (
            "succeeded",
            "failed",
            "cancelled",
        ):
            continue
        finished = float(payload.get("finished_at") or payload.get("created_at") or 0)
        if finished > cutoff:
            continue
        if not args.dry_run:
            with archive.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "id": payload.get("id"),
                            "action": payload.get("action"),
                            "task_id": payload.get("task_id"),
                            "status": payload.get("status"),
                            "finished_at": payload.get("finished_at"),
                            "trace_id": payload.get("trace_id"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            path.unlink(missing_ok=True)
        removed += 1
    payload = {
        "ok": True,
        "removed": removed,
        "dry_run": bool(args.dry_run),
        "archive": str(archive),
    }
    if args.json:
        _emit(payload)
    else:
        print(
            f"{'would prune' if args.dry_run else 'pruned'} {removed} terminal job(s); "
            f"archive: {archive}"
        )
    return 0
