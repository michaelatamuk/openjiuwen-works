"""Readiness gate internals.

The public API is re-exported from the package ``__init__`` so callers keep using
``works.application.execution.readiness``.
"""

from __future__ import annotations

import shlex
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

from works.application.execution.readiness.scan import (
    find_suppressions,
    import_graph,
    import_violations,
)
from works.application.execution.readiness.spec import (
    COMMANDS,
    SPEC_PATH,
    CheckResult,
    Commands,
    ReadinessReport,
    ReportStatus,
    load_spec,
)
from works.application.observability.features import feature_files as mapped_feature_files
from works.application.observability.features import load_feature_maps
from works.domain.errors import ConfigError, PolicyError


def _run_command(repo: Path, command: str, timeout_s: int) -> CheckResult:
    argv = [sys.executable if part == "{python}" else part for part in shlex.split(command)]
    started = time.monotonic()
    try:
        completed = subprocess.run(  # nosec B603
            argv,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("command", "Command", "fail", f"timed out after {timeout_s}s")
    except OSError as exc:
        return CheckResult("command", "Command", "fail", f"could not start: {exc}")
    duration = int((time.monotonic() - started) * 1000)
    output = (completed.stderr or completed.stdout or "").strip().splitlines()
    tail = " Â· ".join(output[-3:])[:500]
    detail = f"exit {completed.returncode} in {duration} ms" + (f": {tail}" if tail else "")
    return CheckResult(
        "command", "Command", "pass" if completed.returncode == 0 else "fail", detail
    )


def assess(
    repo: Path,
    *,
    run_commands: bool = True,
    timeout_s: int = 120,
) -> ReadinessReport:
    repo = repo.resolve()
    spec = load_spec(repo)
    checks: list[CheckResult] = []

    checks.append(
        CheckResult(
            "git",
            "Git repository",
            "pass" if (repo / ".git").exists() else "fail",
            ".git found" if (repo / ".git").exists() else "not a git repository",
        )
    )
    project = next(
        (
            name
            for name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod")
            if (repo / name).exists()
        ),
        None,
    )
    checks.append(
        CheckResult(
            "project",
            "Project manifest",
            "pass" if project else "fail",
            project or "no pyproject/package/Cargo/go module",
        )
    )

    feature_root = spec.features if spec is not None else "features"
    features = [path.name for path in mapped_feature_files(repo, feature_root)]
    try:
        maps = load_feature_maps(repo, feature_root)
    except ConfigError as exc:
        feature_check = CheckResult("features", "Feature map", "fail", str(exc))
    else:
        count = sum(len(feature_map.features) for feature_map in maps)
        feature_check = CheckResult(
            "features",
            "Feature map",
            "pass" if count else "fail",
            f"{count} feature(s) in {len(features)} file(s)" if count else "no features declared",
        )
    checks.append(feature_check)

    suppressions = find_suppressions(repo)
    allow = set(spec.suppressions.allow) if spec is not None else set()
    unknown = [item for item in suppressions if item.location not in allow]
    checks.append(
        CheckResult(
            "suppressions",
            "Known suppressions",
            "pass" if not unknown else "fail",
            f"{len(suppressions)} found, {len(unknown)} unknown" if suppressions else "none found",
        )
    )

    rules = spec.boundaries.rules if spec is not None else []
    violations = import_violations(repo, rules)
    checks.append(
        CheckResult(
            "imports",
            "Import boundaries",
            "pass" if not violations else "fail",
            f"{len(violations)} violation(s)" if violations else f"{len(rules)} rule(s)",
        )
    )

    graph, cycles = import_graph(repo)
    checks.append(
        CheckResult(
            "cycles",
            "Import cycles",
            "pass" if not cycles else "fail",
            f"{len(cycles)} cycle(s)" if cycles else f"{len(graph)} module(s)",
        )
    )

    commands = spec.commands if spec is not None else Commands()
    for command_id, label in COMMANDS:
        command = getattr(commands, command_id)
        if not run_commands:
            checks.append(
                CheckResult(
                    command_id,
                    label,
                    "skip",
                    "not run in the preview; run `works readiness`",
                )
            )
            continue
        if not command:
            checks.append(
                CheckResult(
                    command_id,
                    label,
                    "fail",
                    f"not configured in {SPEC_PATH.as_posix()}",
                )
            )
            continue
        result = _run_command(repo, command, timeout_s)
        checks.append(CheckResult(command_id, label, result.status, result.detail))

    passed = sum(1 for check in checks if check.status == "pass")
    failed = sum(1 for check in checks if check.status == "fail")
    skipped = sum(1 for check in checks if check.status == "skip")
    total = len(checks)
    if failed:
        status: ReportStatus = "fail"
        note = "Red gate: automation must not start until every check is green."
    elif skipped:
        status = "partial"
        note = "Static checks only; run `works readiness` to execute the configured commands."
    else:
        status = "pass"
        note = "Green: the repository is ready for autonomous work."
    if spec is None:
        note = f"No {SPEC_PATH.as_posix()} found. Add one before autonomy."
    return ReadinessReport(
        status=status,
        checks=checks,
        passed=passed,
        failed=failed,
        skipped=skipped,
        total=total,
        suppressions=suppressions,
        unknown_suppressions=unknown,
        feature_files=features,
        import_cycles=cycles,
        import_edges=graph,
        note=note,
    )


def ensure_ready(repo: Path, *, timeout_s: int = 120) -> ReadinessReport:
    """Run the full gate; a red report is a refusal, not a warning."""
    report = assess(repo, run_commands=True, timeout_s=timeout_s)
    if report.status == "fail":
        failed = ", ".join(check.id for check in report.checks if check.status == "fail")
        raise PolicyError(f"readiness is red ({failed}); run `works readiness` before automation")
    return report
