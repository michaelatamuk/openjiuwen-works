"""Lockfile readers: what is pinned in a repository, and in which ecosystem."""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9_.@/-]+$")
REQUIREMENTS = ("requirements.txt", "requirements-dev.txt", "requirements-prod.txt")


@dataclass(frozen=True)
class LockedPackage:
    name: str
    version: str
    ecosystem: str
    source: str


def normalize(name: str) -> str:
    return name.strip().lower().replace("_", "-").replace(".", "-")


def _from_requirements(path: Path) -> list[LockedPackage]:
    packages: list[LockedPackage] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        name = name.split("[", 1)[0].strip()
        version = version.strip().split(";", 1)[0].strip()
        if not name or not version or not _NAME.match(name):
            continue
        if any(marker in version for marker in ("<", ">", "!", "~", ",", "*")):
            continue
        packages.append(LockedPackage(name, version, "PyPI", path.name))
    return packages


def _from_toml(path: Path) -> list[LockedPackage]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    entries = payload.get("package")
    if not isinstance(entries, list):
        return []
    packages: list[LockedPackage] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        version = str(entry.get("version") or "").strip()
        if name and version:
            packages.append(LockedPackage(name, version, "PyPI", path.name))
    return packages


def _npm_name(key: str) -> str:
    marker = "node_modules/"
    if marker in key:
        return key.rsplit(marker, 1)[1]
    return key


def _from_package_lock(path: Path) -> list[LockedPackage]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    packages: list[LockedPackage] = []
    entries = payload.get("packages")
    if isinstance(entries, dict):
        for key, value in entries.items():
            if not key or not isinstance(value, dict):
                continue
            version = str(value.get("version") or "").strip()
            name = _npm_name(str(key))
            if name and version:
                packages.append(LockedPackage(name, version, "npm", path.name))
        return packages
    dependencies = payload.get("dependencies")
    if isinstance(dependencies, dict):
        for name, value in dependencies.items():
            if not isinstance(value, dict):
                continue
            version = str(value.get("version") or "").strip()
            if name and version:
                packages.append(LockedPackage(str(name), version, "npm", path.name))
    return packages


def read_lockfiles(repo: Path) -> tuple[list[LockedPackage], list[str]]:
    """Pinned packages and the files they came from; unknown files are skipped silently."""
    found: list[LockedPackage] = []
    files: list[str] = []
    for name in ("uv.lock", "poetry.lock"):
        path = repo / name
        if path.is_file():
            found.extend(_from_toml(path))
            files.append(name)
    for name in REQUIREMENTS:
        path = repo / name
        if path.is_file():
            found.extend(_from_requirements(path))
            files.append(name)
    lock = repo / "package-lock.json"
    if lock.is_file():
        found.extend(_from_package_lock(lock))
        files.append(lock.name)
    seen: set[tuple[str, str, str]] = set()
    unique: list[LockedPackage] = []
    for item in found:
        key = (normalize(item.name), item.version, item.ecosystem)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique, files
