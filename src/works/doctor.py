"""works doctor: what is installed, what is configured, what is missing."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess  # nosec B404
import sys
import urllib.request
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
    try:
        sdk = importlib.util.find_spec("claude_agent_sdk")
    except (ImportError, ModuleNotFoundError):
        sdk = None
    native = None
    if sdk is not None and sdk.origin:
        candidate = Path(sdk.origin).parent / "_bundled" / "claude.exe"
        native = str(candidate) if candidate.exists() else None
    if spec is not None and sdk is not None and native is not None:
        return CheckResult(
            name="harness",
            status="ok",
            detail=f"live ready: openjiuwen + claude-agent-sdk + {native}",
        )
    missing = []
    if spec is None:
        missing.append("openjiuwen.harness_protocol")
    if sdk is None:
        missing.append("claude-agent-sdk")
    if sdk is not None and native is None:
        missing.append("bundled claude.exe")
    return CheckResult(
        name="harness",
        status="warn",
        detail=f"fake harness in use; missing: {', '.join(missing)}",
    )


def _ppma_check(environ: dict[str, str]) -> CheckResult:
    url = environ.get("WORKS_PPMA_URL")
    if not url:
        return CheckResult(
            name="ppma",
            status="warn",
            detail="WORKS_PPMA_URL not set; runs are not reported to PPMA memory",
        )
    token = environ.get("WORKS_PPMA_TOKEN") or environ.get("PPMA_OWNER_TOKEN") or "dev"
    request = urllib.request.Request(  # noqa: S310  # nosec B310
        f"{url.rstrip('/')}/v0/spaces/me/memory/views",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310  # nosec B310
            if response.status == 200:
                return CheckResult(name="ppma", status="ok", detail=f"reachable at {url}")
            return CheckResult(
                name="ppma", status="warn", detail=f"{url} returned {response.status}"
            )
    except Exception as exc:
        return CheckResult(name="ppma", status="warn", detail=f"{url}: {exc}")


def _container_check() -> CheckResult:
    found = _which("docker") or _which("podman")
    if not found:
        return CheckResult(
            name="container",
            status="warn",
            detail="docker/podman not found; --verifier docker is unavailable",
        )
    if _which("podman") and not _which("docker"):
        return CheckResult(name="container", status="ok", detail=found)
    try:
        probe = subprocess.run(  # noqa: S603  # nosec B603
            [found, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult(
            name="container",
            status="warn",
            detail=f"{found} did not answer in time: {exc}",
        )
    if probe.returncode == 0:
        return CheckResult(
            name="container",
            status="ok",
            detail=f"{found} (daemon {probe.stdout.strip() or 'reachable'})",
        )
    return CheckResult(
        name="container",
        status="warn",
        detail=f"{found} is installed but the daemon is not reachable; start Docker Desktop",
    )


def _credentials_check(environ: dict[str, str]) -> CheckResult:
    builder = environ.get("ANTHROPIC_API_KEY") or environ.get("WORKS_MODEL_KEY")
    verifier = environ.get("WORKS_VERIFIER_API_KEY")
    if builder and verifier:
        return CheckResult(
            name="credentials", status="ok", detail="builder and verifier keys are set"
        )
    missing = []
    if not builder:
        missing.append("ANTHROPIC_API_KEY / WORKS_MODEL_KEY (builder)")
    if not verifier:
        missing.append("WORKS_VERIFIER_API_KEY (verifier, M2)")
    return CheckResult(
        name="credentials",
        status="warn",
        detail=f"missing: {', '.join(missing)}; the fake harness needs none",
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
        _ppma_check(environment),
        _container_check(),
        _credentials_check(environment),
        _scenario_check(paths, repo),
        _quarantine_check(repo),
    ]


def failed(results: list[CheckResult]) -> bool:
    return any(result.status == "fail" and result.required for result in results)
