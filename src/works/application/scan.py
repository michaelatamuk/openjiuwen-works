"""Proactive scan: run a repository check, keep a baseline, file only new failures.

The scan is explicit, local and deterministic. It never starts a run and never opens a gate: it
creates one task per newly failing check, with the command and the failure as the reproduction hint.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from works.adapters.processes.runner import CommandResult, CommandRunner
from works.adapters.queue.atomic import atomic_write
from works.adapters.queue.store import Queue
from works.config.paths import WorksPaths
from works.domain.enums import SourceKind
from works.domain.task import Source

_FAILURE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)
TAIL_LINES = 20


@dataclass(frozen=True)
class ScanResult:
    command: str
    exit_code: int
    failures: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)
    baseline_written: bool = False


def parse_failures(output: str) -> list[str]:
    """Failure ids from pytest-style lines; deduplicated and ordered."""
    return list(dict.fromkeys(_FAILURE.findall(output)))


def _synthetic(output: str, exit_code: int) -> str:
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    digest = hashlib.sha256(f"{exit_code}\n{tail}".encode()).hexdigest()[:8]
    return f"command-{digest}"


def _digest(repo: Path, command: str) -> str:
    return hashlib.sha256(f"{repo.resolve()}\n{command}".encode()).hexdigest()[:16]


def baseline_path(paths: WorksPaths, repo: Path, command: str) -> Path:
    return paths.state / "scan" / f"{_digest(repo, command)}.json"


def _load(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    failures = payload.get("failures") if isinstance(payload, dict) else None
    return [str(item) for item in failures] if isinstance(failures, list) else []


def _save(path: Path, repo: Path, command: str, failures: list[str], exit_code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "repo": str(repo.resolve()),
        "command": command,
        "exit_code": exit_code,
        "failures": failures,
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }
    atomic_write(path, json.dumps(payload, indent=2) + "\n")


def _source(repo: Path, command: str, failure: str) -> Source:
    return Source(
        kind=SourceKind.DETECTOR,
        ref=f"scan:{failure}",
        title=f"scan: {failure}",
        severity="S3",
        labels=["scan"],
        channel="scan",
        reproduction_hint=(
            f"Run `{command}` in {repo.name or repo}; `{failure}` failed in the latest scan."
        ),
        dedupe_key=f"scan:{_digest(repo, command)}:{failure}",
    )


def scan_repository(
    paths: WorksPaths,
    repo: Path,
    command: str,
    *,
    runner: CommandRunner,
    product: str = "openjiuwen",
    timeout_s: int = 600,
    dry_run: bool = False,
    queue: Queue | None = None,
) -> ScanResult:
    """Run the command once; compare with the baseline; file the new failures."""
    argv = [part.strip('"').replace("{python}", _python()) for part in _split(command)]
    if not argv:
        raise ValueError("a scan needs a command")
    baseline_file = baseline_path(paths, repo, command)
    previous = _load(baseline_file)
    result: CommandResult = runner.run(argv, repo, timeout_s=timeout_s)
    output = f"{result.stdout}\n{result.stderr}"
    failures = parse_failures(output) if not result.ok else []
    if not result.ok and not failures:
        failures = [_synthetic(output, result.exit_code)]
    new = [item for item in failures if item not in previous]
    fixed = [item for item in previous if item not in failures]
    queue = queue or Queue(paths)
    created: list[str] = []
    existing: list[str] = []
    if not dry_run:
        for failure in new:
            task, is_new = queue.submit(
                source=_source(repo, command, failure),
                flow="fix-issue",
                product=product,
                repo=str(repo),
            )
            (created if is_new else existing).append(task.id)
        _save(baseline_file, repo, command, failures, result.exit_code)
    return ScanResult(
        command=command,
        exit_code=result.exit_code,
        failures=failures,
        new=new,
        fixed=fixed,
        created=created,
        existing=existing,
        baseline_written=not dry_run,
    )


def _split(command: str) -> list[str]:
    import shlex

    return shlex.split(command, posix=False)


def _python() -> str:
    import sys

    return sys.executable
