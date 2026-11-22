"""Run checks either on the host or in an isolated container.

The verifier is the party that judges a change, so it must not share the builder's credentials,
network or filesystem. `DockerVerifier` is that boundary: the worktree is mounted, the network is
off, capabilities are dropped, and only the command's own output comes back.

The local verifier stays the default. A container run is opt-in (`--verifier docker`) so a machine
without a running Docker daemon never pretends to have isolated verification.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from .errors import ConfigError
from .runner import CommandResult, CommandRunner

DEFAULT_IMAGE = "python:3.12-slim"


@runtime_checkable
class Verifier(Protocol):
    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
        timeout_s: int = 600,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class Mount:
    """A host directory exposed inside the container."""

    host: Path
    target: str
    read_only: bool = True


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _rewrite_path(value: str, mounts: tuple[Mount, ...]) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        return value
    for mount in mounts:
        if _under(candidate, mount.host):
            relative = candidate.relative_to(mount.host).as_posix()
            return mount.target if relative == "." else f"{mount.target.rstrip('/')}/{relative}"
    return value


class LocalVerifier:
    name = "local"
    isolation = "process"

    def __init__(self, runner: CommandRunner) -> None:
        self._runner = runner

    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
        timeout_s: int = 600,
    ) -> CommandResult:
        return self._runner.run(argv, cwd, env=env, timeout_s=timeout_s)


@dataclass(frozen=True)
class ContainerPolicy:
    network: str = "none"
    memory: str = "2g"
    cpus: str = "1.0"
    pids_limit: int = 512
    tmpfs: tuple[str, ...] = ("/tmp",)  # noqa: S108  # nosec B108


@dataclass(frozen=True)
class DockerVerifier:
    """A `docker run` wrapper that keeps the container away from the host.

    Paths under a mount are rewritten to their container location, both in `argv` and in `env`
    values, so a scenario or a test command that names an absolute host path still works.
    """

    runner: CommandRunner
    image: str = DEFAULT_IMAGE
    mounts: tuple[Mount, ...] = ()
    policy: ContainerPolicy = field(default_factory=ContainerPolicy)
    name: str = "docker"
    isolation: str = "container"

    def available(self) -> bool:
        result = self.runner.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            Path.cwd(),
            timeout_s=15,
        )
        return result.ok

    def _environment(self, env: Mapping[str, str] | None) -> list[str]:
        parts: list[str] = []
        for key, value in (env or {}).items():
            rendered = _rewrite_path(value, self.mounts)
            parts.extend(["-e", f"{key}={rendered}"])
        return parts

    def docker_argv(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
    ) -> list[str]:
        if not self.mounts:
            raise ConfigError("a container verifier needs at least one mount")
        workdir = _rewrite_path(str(cwd), self.mounts)
        if workdir == str(cwd):
            raise ConfigError(
                f"{cwd} is outside every verifier mount; add a mount or use --verifier local"
            )
        command: list[str] = [
            "docker",
            "run",
            "--rm",
            "--init",
            f"--network={self.policy.network}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--memory={self.policy.memory}",
            f"--cpus={self.policy.cpus}",
            f"--pids-limit={self.policy.pids_limit}",
            "-w",
            workdir,
        ]
        for mount in self.mounts:
            suffix = ":ro" if mount.read_only else ""
            command.extend(["-v", f"{mount.host}:{mount.target}{suffix}"])
        for location in self.policy.tmpfs:
            command.extend(["--tmpfs", location])
        command.extend(self._environment(env))
        command.append(self.image)
        command.extend(_rewrite_path(item, self.mounts) for item in argv)
        return command

    def run(
        self,
        argv: list[str],
        cwd: Path,
        *,
        env: dict[str, str] | None = None,
        timeout_s: int = 600,
    ) -> CommandResult:
        return self.runner.run(
            self.docker_argv(argv, cwd, env=env),
            cwd,
            timeout_s=timeout_s + 60,
        )


def verifier_from_name(
    name: str,
    runner: CommandRunner,
    *,
    image: str | None = None,
    mounts: tuple[Mount, ...] = (),
) -> Verifier:
    if name == "local":
        return LocalVerifier(runner)
    if name != "docker":
        raise ConfigError(f"unknown verifier {name!r}; expected local or docker")
    resolved = image or os.environ.get("WORKS_VERIFIER_IMAGE") or DEFAULT_IMAGE
    return DockerVerifier(runner=runner, image=resolved, mounts=mounts)
