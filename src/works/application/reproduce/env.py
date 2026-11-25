"""Per-repository environments for reproduction (venv / node_modules).

Installation is explicit (`works reproduce prepare`), because a run should not silently download
dependencies. The fingerprint is recorded either way, so the proof says what the check ran with.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from works.adapters.processes.runner import CommandRunner, SubprocessRunner
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError

LOCKFILES = (
    "uv.lock",
    "requirements.txt",
    "poetry.lock",
    "package-lock.json",
    "go.sum",
    "Cargo.lock",
)


@dataclass(frozen=True)
class EnvironmentPlan:
    kind: str
    directory: Path
    commands: list[list[str]] = field(default_factory=list)
    fingerprint: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _hash(path: Path) -> str:
    if not path.is_file():
        return "none"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _python(paths: WorksPaths, repo: Path) -> EnvironmentPlan:
    directory = paths.root / "envs" / repo.name
    python = directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    commands: list[list[str]] = []
    if not python.exists():
        commands.append([sys.executable, "-m", "venv", str(directory)])
    target = str(python)
    if (repo / "requirements.txt").is_file():
        commands.append([target, "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    elif (repo / "pyproject.toml").is_file():
        commands.append([target, "-m", "pip", "install", "-q", "-e", "."])
    return EnvironmentPlan("python", directory, commands, fingerprint(paths, repo))


def fingerprint(_paths: WorksPaths, repo: Path) -> dict[str, str]:
    data = {"python": sys.version.split()[0]}
    for name in LOCKFILES:
        path = repo / name
        if path.is_file():
            data[name] = _hash(path)
    return data


def plan(paths: WorksPaths, repo: Path) -> EnvironmentPlan:
    if (repo / "package-lock.json").is_file():
        return EnvironmentPlan("node", repo, [["npm", "ci", "--silent"]], fingerprint(paths, repo))
    if (repo / "package.json").is_file():
        return EnvironmentPlan(
            "node", repo, [["npm", "install", "--silent"]], fingerprint(paths, repo)
        )
    if any((repo / name).is_file() for name in ("pyproject.toml", "requirements.txt")):
        return _python(paths, repo)
    for kind, marker in (("go", "go.mod"), ("rust", "Cargo.toml"), ("java", "pom.xml")):
        if (repo / marker).is_file():
            return EnvironmentPlan(kind, repo, [], fingerprint(paths, repo))
    return EnvironmentPlan("unknown", repo, [], fingerprint(paths, repo), ["no known manifest"])


def prepare(
    paths: WorksPaths, repo: Path, *, runner: CommandRunner | None = None, offline: bool = False
) -> EnvironmentPlan:
    plan_ = plan(paths, repo)
    if not plan_.commands:
        return plan_
    if offline:
        raise ConfigError("offline mode: the environment still needs an install step")
    command_runner = runner or SubprocessRunner()
    for command in plan_.commands:
        result = command_runner.run(command, repo, timeout_s=1800)
        if not result.ok:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            reason = detail[-1] if detail else result.exit_code
            raise ConfigError(f"environment step {command[0]} failed: {reason}")
    return plan_
