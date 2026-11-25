"""How to check a repository: config first, then the ecosystem, then the signal.

The result is advice for stage 2: the flow still owns execution. Every detection names its source so
the proof says whether a person configured the command or Works guessed it from a manifest.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from works.domain.errors import ConfigError

OVERRIDE = Path(".works") / "reproduce.yaml"

ECOSYSTEMS: tuple[tuple[str, tuple[str, ...], list[str]], ...] = (
    (
        "python",
        ("pyproject.toml", "requirements.txt", "setup.py"),
        [sys.executable, "-m", "pytest", "-q"],
    ),
    ("node", ("package.json", "package-lock.json"), ["npm", "test", "--silent"]),
    ("go", ("go.mod",), ["go", "test", "./..."]),
    ("rust", ("Cargo.toml",), ["cargo", "test", "-q"]),
    ("java", ("pom.xml",), ["mvn", "-q", "test"]),
)


@dataclass(frozen=True)
class Detection:
    command: list[str]
    source: str
    reason: str


def from_signal(hint: str | None) -> Detection | None:
    """A stack trace or a failing test name narrows the check; free text does not."""
    if not hint:
        return None
    text = hint.strip()
    failed = re.search(r"FAILED\s+([\w./\\-]+::[\w\[\].:-]+)", text)
    if failed:
        return Detection(
            [sys.executable, "-m", "pytest", failed.group(1), "-q"],
            "signal",
            "the report names a failing pytest node",
        )
    node = re.search(r"\b((?:[\w.-]+/)+[\w.-]+\.py::[\w\[\].:-]+)", text)
    if node:
        return Detection(
            [sys.executable, "-m", "pytest", node.group(1), "-q"],
            "signal",
            "the report names a test node",
        )
    command = re.search(r"`([^`]{3,200})`", text)
    if command:
        return Detection(
            ["/bin/sh", "-c", command.group(1)]
            if sys.platform != "win32"
            else ["cmd", "/c", command.group(1)],
            "signal",
            "the report quotes a command",
        )
    return None


def from_repo(repo: Path) -> Detection | None:
    override = repo / OVERRIDE
    if override.is_file():
        try:
            payload = yaml.safe_load(override.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"{override} is not valid YAML: {exc}") from exc
        command = payload.get("command") if isinstance(payload, dict) else None
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) for item in command)
        ):
            raise ConfigError(f"{override}: command must be a non-empty list of strings")
        return Detection(list(command), "repo-config", f"{OVERRIDE.as_posix()} sets the command")
    for name, markers, command in ECOSYSTEMS:
        if any((repo / marker).exists() for marker in markers):
            return Detection(list(command), "detected", f"{name} manifest found")
    return None


def choose(repo: Path, hint: str | None) -> Detection | None:
    """Config beats a narrowed signal, which beats a generic ecosystem guess."""
    configured = from_repo(repo)
    if configured is not None and configured.source == "repo-config":
        return configured
    narrowed = from_signal(hint)
    if narrowed is not None:
        return narrowed
    return configured
