"""Deploy the delivered commit to the environment where the signal was seen.

Gate 2 and delivery have already happened. This module does not approve, merge or re-run the
verifier; it consumes the delivered commit and runs one owner-approved command. The command is
either passed explicitly or read from the product map. A dry run records the intent without
touching the target.

The deployment record is idempotent per task, run, commit and environment. A failed deployment is
never reported as deployed; a retry is a new record and must be requested explicitly with
`--force` only when the previous record is already successful.
"""

from __future__ import annotations

import json
import os
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import WorksPaths
from .errors import ConfigError
from .products import deploy_command
from .queue import Queue
from .records import TaskState
from .release import latest_run_dir
from .runner import CommandRunner, SubprocessRunner

STATUS = Literal["deployed", "failed", "dry_run"]

_DELIVERY_FILE = "delivery.json"
_DEPLOY_FILE = "deployment.json"


class Deployment(BaseModel):
    schema_version: int = 1
    task_id: str
    run_id: str
    commit: str
    environment: str = "staging"
    command: list[str]
    status: STATUS
    exit_code: int = 0
    output_tail: str = ""
    dry_run: bool = False
    created: bool = True
    notes: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_id": self.run_id,
            "commit": self.commit,
            "environment": self.environment,
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "output_tail": self.output_tail,
            "dry_run": self.dry_run,
            "created": self.created,
            "notes": self.notes,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


def _read_delivery(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / _DELIVERY_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    return data if isinstance(data, dict) else None


def _existing(run_dir: Path) -> Deployment | None:
    path = run_dir / _DEPLOY_FILE
    if not path.exists():
        return None
    try:
        return Deployment.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(run_dir: Path, deployment: Deployment) -> None:
    (run_dir / _DEPLOY_FILE).write_text(
        deployment.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def parse_command(value: str | list[str]) -> list[str]:
    """A command is an argv list, a JSON array or a quoted string. Never a shell."""
    if isinstance(value, list):
        argv = [str(item) for item in value]
    elif value.lstrip().startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"deploy command is not a JSON array: {exc}") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ConfigError("deploy command must be a JSON array of strings")
        argv = parsed
    else:
        argv = shlex.split(value, posix=os.name != "nt")
    if not argv or not all(item.strip() for item in argv):
        raise ConfigError("deploy command is empty")
    return argv


def _env(task_id: str, run_id: str, commit: str, environment: str, dry_run: bool) -> dict[str, str]:
    return {
        "WORKS_TASK_ID": task_id,
        "WORKS_RUN_ID": run_id,
        "WORKS_COMMIT": commit,
        "WORKS_ENVIRONMENT": environment,
        "WORKS_DEPLOY_DRY_RUN": "1" if dry_run else "0",
    }


def deploy(
    paths: WorksPaths,
    task_id: str,
    *,
    command: str | list[str] | None = None,
    environment: str = "staging",
    dry_run: bool = False,
    force: bool = False,
    runner: CommandRunner | None = None,
) -> Deployment:
    """Run the deploy command for the already-delivered commit.

    A deploy after a release but before delivery is refused: the release proof is bound to the
    base commit, and deploying that would ship the unfixed code.
    """
    queue = Queue(paths)
    task = queue.load(task_id)
    if task.state is not TaskState.RELEASED:
        raise ConfigError(f"deploy runs after release; task {task_id} is {task.state.value}")
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        raise ConfigError(f"task {task_id} has no finished run")
    delivery = _read_delivery(run_dir)
    if delivery is None or not delivery.get("commit"):
        raise ConfigError(f"task {task_id} has not been delivered; run `works deliver` first")
    if not dry_run and not delivery.get("pushed"):
        raise ConfigError(
            f"task {task_id} was delivered locally but not pushed; deploy needs the pushed commit"
        )
    commit = str(delivery["commit"])
    run_id = str(delivery.get("run_id") or run_dir.name)
    argv = parse_command(command) if command is not None else deploy_command(paths, task.product)
    if argv is None:
        raise ConfigError(
            "no deploy command: pass --command or add `deploy:` to the product in "
            ".works/products.yaml"
        )

    previous = _existing(run_dir)
    already_done = previous is not None and (
        previous.status == "deployed" or (previous.status == "dry_run" and dry_run)
    )
    if (
        already_done
        and not force
        and previous is not None
        and previous.commit == commit
        and previous.environment == environment
    ):
        previous.created = False
        previous.notes.append("already recorded; nothing to do")
        return previous

    started = datetime.now(tz=UTC)
    deployment = Deployment(
        task_id=task_id,
        run_id=run_id,
        commit=commit,
        environment=environment,
        command=argv,
        status="dry_run" if dry_run else "deployed",
        dry_run=dry_run,
        started_at=started,
        finished_at=started,
    )
    if dry_run:
        deployment.notes.append("dry run: the target was not touched")
        _write(run_dir, deployment)
        queue.append(
            task_id,
            "deploy.finished",
            {
                "status": deployment.status,
                "commit": commit,
                "environment": environment,
                "dry_run": True,
            },
        )
        return deployment

    command_runner = runner or SubprocessRunner()
    result = command_runner.run(
        argv,
        Path(task.repo),
        env=_env(task_id, run_id, commit, environment, dry_run),
        timeout_s=600,
    )
    deployment.exit_code = result.exit_code
    deployment.output_tail = result.output[-4000:]
    deployment.status = "deployed" if result.ok else "failed"
    deployment.finished_at = datetime.now(tz=UTC)
    _write(run_dir, deployment)
    queue.append(
        task_id,
        "deploy.finished",
        {
            "status": deployment.status,
            "commit": commit,
            "environment": environment,
            "exit_code": result.exit_code,
            "dry_run": False,
        },
    )
    return deployment
