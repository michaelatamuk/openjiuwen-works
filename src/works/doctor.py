"""works doctor: what is installed, what is configured, what is missing."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .config import WorksPaths
from .errors import WorksError
from .flow import find_flow, load_flow

Status = Literal["ok", "warn", "fail"]


class CheckResult(BaseModel):
    name: str
    status: Status
    detail: str
    required: bool = False


def _which(name: str) -> str | None:
    return shutil.which(name)


def _python_check() -> CheckResult:
    version = sys.version_info
    detail = f"{version.major}.{version.minor}.{version.micro} at {sys.executable}"
    ok = (3, 11) <= (version.major, version.minor) < (3, 14)
    return CheckResult(name="python", status="ok" if ok else "fail", detail=detail, required=True)


def _git_check() -> CheckResult:
    found = _which("git")
    return CheckResult(
        name="git",
        status="ok" if found else "fail",
        detail=found or "git is not on PATH",
        required=True,
    )


def _root_check(paths: WorksPaths) -> CheckResult:
    probe = paths.root / ".works-write-probe"
    try:
        paths.root.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return CheckResult(
            name="workspace", status="fail", detail=f"{paths.root}: {exc}", required=True
        )
    return CheckResult(name="workspace", status="ok", detail=str(paths.root), required=True)


def _flow_check(paths: WorksPaths) -> CheckResult:
    try:
        flow = load_flow(find_flow(paths.flows, "fix-issue"))
    except WorksError as exc:
        return CheckResult(name="flow", status="warn", detail=str(exc))
    return CheckResult(name="flow", status="ok", detail=f"fix-issue: {len(flow.nodes)} nodes")


def _harness_check() -> CheckResult:
    try:
        spec = importlib.util.find_spec("openjiuwen.harness_protocol")
    except (ImportError, ModuleNotFoundError):
        spec = None
    if spec is None:
        return CheckResult(
            name="harness",
            status="warn",
            detail="openjiuwen.harness_protocol not importable; the fake harness is in use",
        )
    return CheckResult(name="harness", status="ok", detail=str(spec.origin))


def _container_check() -> CheckResult:
    found = _which("docker") or _which("podman")
    return CheckResult(
        name="container",
        status="ok" if found else "warn",
        detail=found or "docker/podman not found; the verifier container lands in M2",
    )


def _credentials_check(environ: dict[str, str]) -> CheckResult:
    names = ("WORKS_BUILDER_API_KEY", "WORKS_VERIFIER_API_KEY")
    present = [name for name in names if environ.get(name)]
    if len(present) == 2:
        return CheckResult(name="credentials", status="ok", detail="both provider keys set")
    return CheckResult(
        name="credentials",
        status="warn",
        detail=f"missing: {', '.join(name for name in names if name not in present)}; "
        "not needed for the fake harness",
    )


def _scenario_check(paths: WorksPaths, repo: Path | None) -> CheckResult:
    directory = paths.scenarios
    if not directory.exists():
        return CheckResult(
            name="scenarios",
            status="warn",
            detail=f"not found: {directory} (expected outside the repository)",
        )
    if repo is not None and directory.resolve().is_relative_to(repo.resolve()):
        return CheckResult(
            name="scenarios", status="fail", detail=f"{directory} is inside the repository"
        )
    return CheckResult(name="scenarios", status="ok", detail=str(directory))


def _quarantine_check(repo: Path | None) -> CheckResult:
    if repo is None:
        return CheckResult(name="quarantine", status="warn", detail="no repository given")
    inside = repo / "quarantine.json"
    if inside.exists():
        return CheckResult(
            name="quarantine",
            status="fail",
            detail=f"{inside} is inside the repository; it must live outside",
        )
    return CheckResult(name="quarantine", status="ok", detail="outside the repository")


def run_checks(
    paths: WorksPaths,
    *,
    repo: Path | None = None,
    environ: dict[str, str] | None = None,
) -> list[CheckResult]:
    environment = dict(os.environ if environ is None else environ)
    return [
        _python_check(),
        _git_check(),
        _root_check(paths),
        _flow_check(paths),
        _harness_check(),
        _container_check(),
        _credentials_check(environment),
        _scenario_check(paths, repo),
        _quarantine_check(repo),
    ]


def failed(results: list[CheckResult]) -> bool:
    return any(result.status == "fail" and result.required for result in results)
