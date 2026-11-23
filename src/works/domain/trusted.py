"""Checks outlive changes. Read the judge from the base commit, never the worktree."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from works.adapters.git.repo import GitRepo
from works.domain.errors import ConfigError
from works.domain.flow import FlowSpec, find_flow, load_flow_text
from works.domain.policy import matches

CHECK_FILES = (
    "src/works/policy.py",
    "src/works/state.py",
    "src/works/scenarios.py",
)
CHECK_PATHS = ("flows/", *CHECK_FILES)
_INSTALLED_CHECKS = {
    "src/works/policy.py": "domain/policy.py",
    "src/works/state.py": "domain/state.py",
    "src/works/scenarios.py": "application/execution/scenarios.py",
}


def is_check_path(path: str) -> bool:
    return matches(path, CHECK_PATHS)


@dataclass(frozen=True)
class TrustedFlow:
    flow: FlowSpec
    source: str
    checks_sha: str


def checks_digest(*parts: str) -> str:
    payload = "\n---\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_at(repo: GitRepo, base: str, relative: str, fallback: Path) -> tuple[str, str]:
    text = repo.show(base, relative)
    if text is not None:
        return text, f"git:{base}:{relative}"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8"), f"workspace:{fallback}"
    raise ConfigError(f"trusted check not found at {base}:{relative} and no fallback exists")


def load_trusted_flow(
    repo: GitRepo,
    base: str,
    name: str,
    flows_dir: Path,
) -> TrustedFlow:
    """Load the flow from the base commit when it is tracked there; otherwise the workspace.

    The digest covers the flow and the check modules, so a resumed run can prove it is still
    judged by the same rules.
    """
    relative = f"flows/{name}.yaml"
    text = repo.show(base, relative)
    if text is not None:
        source = f"git:{base}:{relative}"
    else:
        path = find_flow(flows_dir, name)
        text = path.read_text(encoding="utf-8")
        source = f"workspace:{path}"
    flow = load_flow_text(text, source=source)

    parts = [text]
    for relative_check in CHECK_FILES:
        installed = Path(__file__).resolve().parents[1] / _INSTALLED_CHECKS[relative_check]
        check_text, _ = _read_at(repo, base, relative_check, installed)
        parts.append(check_text)
    return TrustedFlow(flow=flow, source=source, checks_sha=checks_digest(*parts))
