"""Evidence is computed, not narrated. A proof page is a pure function of one run."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .decision import GateVerdict
from .gitops import DiffStat
from .policy import PolicyReport, Violation
from .records import (
    Challenge,
    CommandRecord,
    Finding,
    Priority,
    StopReason,
    TaskState,
    Verdict,
)
from .risk import RiskRating

MAX_DIFF_CHARS = 60_000


class DiffStatRow(BaseModel):
    path: str
    added: int
    removed: int

    @classmethod
    def from_stat(cls, stat: DiffStat) -> DiffStatRow:
        return cls(path=stat.path, added=stat.added, removed=stat.removed)


class Artifact(BaseModel):
    kind: str
    path: str
    sha256: str
    description: str = ""


class Evidence(BaseModel):
    schema_version: int = 1
    run_id: str
    task_id: str
    flow: str
    product: str
    source: str
    task_kind: str = "fix"
    base_commit: str | None = None
    checks_sha: str | None = None
    state: TaskState
    stop_reason: StopReason
    model: str | None = None
    provider: str | None = None
    verifier: str = "local"
    verifier_isolation: str = "process"
    prompt_name: str | None = None
    prompt_sha256: str | None = None
    tokens: int = 0
    usd: float = 0.0
    duration_ms: int = 0
    files_changed: list[str] = Field(default_factory=list)
    diff_stat: list[DiffStatRow] = Field(default_factory=list)
    policy: PolicyReport = Field(default_factory=lambda: PolicyReport(ok=True))
    risk: RiskRating | None = None
    decision: GateVerdict | None = None
    reproduce: CommandRecord | None = None
    test: CommandRecord | None = None
    preview: CommandRecord | None = None
    verdict: Verdict | None = None
    challenge: Challenge | None = None
    findings: list[Finding] = Field(default_factory=list)
    features: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    memory_recall: list[str] = Field(default_factory=list)
    would_block: list[str] = Field(default_factory=list)
    not_tested: list[str] = Field(default_factory=list)
    diff: str = ""
    diff_sha256: str = ""
    proof_sha256: str = ""

    def bind(self) -> Evidence:
        """Bind the page to its own content and to the diff."""
        diff_hash = hashlib.sha256(self.diff.encode("utf-8")).hexdigest()
        payload = self.model_copy(update={"diff_sha256": diff_hash, "proof_sha256": ""})
        canonical = payload.model_dump_json(exclude={"proof_sha256"})
        proof_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.model_copy(update={"diff_sha256": diff_hash, "proof_sha256": proof_hash})


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _result(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def render_markdown(evidence: Evidence) -> str:
    verdict = evidence.verdict
    lines: list[str] = [
        f"# Proof — {evidence.task_id}",
        "",
        f"**Run** `{evidence.run_id}` · **Flow** `{evidence.flow}` · "
        f"**Product** `{evidence.product}`",
        "",
        f"**Source** `{evidence.source}` · **Base commit** `{evidence.base_commit or '—'}`",
        "",
        f"**Task kind** `{evidence.task_kind}`",
        "",
        f"**Checks SHA-256** `{evidence.checks_sha or '—'}`",
        "",
        f"**State** `{evidence.state.value}` · **Stop reason** `{evidence.stop_reason.value}`",
        "",
        f"**Proof SHA-256** `{evidence.proof_sha256 or 'unbound'}`",
        "",
    ]
    if verdict is None:
        lines += ["## Verdict", "", "No verdict was produced.", ""]
    else:
        decision = "ALLOW" if verdict.allow else "BLOCK"
        lines += [
            "## Verdict",
            "",
            f"**{decision}** — {_cell(verdict.reason)}.",
            "",
            "| Scenario | Priority | Result | Exit | Duration (ms) |",
            "|---|---|---|---|---|",
        ]
        for outcome in verdict.outcomes:
            lines.append(
                f"| `{_cell(outcome.id)}` | {outcome.priority.value} | "
                f"{_result(outcome.passed)} | {outcome.exit_code} | {outcome.duration_ms} |"
            )
        lines.append("")
    if evidence.decision is not None:
        gate_decision = evidence.decision
        approval = "required" if gate_decision.requires_approval else "not required"
        lines += [
            "## Decision",
            "",
            f"**{gate_decision.verb.upper()}** — `{_cell(gate_decision.reason_code)}` · "
            f"confidence `{gate_decision.confidence:.2f}` · approval {approval}",
            "",
            f"Source `{gate_decision.source}` · id `{gate_decision.decision_id or '—'}` · "
            f"trace `{gate_decision.trace_id or '—'}`",
            "",
        ]
        if gate_decision.alternatives:
            lines += [f"- Alternative: `{_cell(item)}`" for item in gate_decision.alternatives]
            lines.append("")
    if evidence.risk is not None:
        risk = evidence.risk
        lines += [
            "## Risk",
            "",
            f"**{risk.level.value.upper()}** — {risk.files} file(s), {risk.lines} line(s).",
            "",
        ]
        lines += [f"- {_cell(reason)}" for reason in risk.reasons]
        if risk.owners:
            lines.append(f"- Owners: {', '.join(f'`{_cell(owner)}`' for owner in risk.owners)}")
        lines.append("")
    lines += ["## Findings", ""]
    if evidence.findings:
        lines += [
            "| Step | Finding | Confidence | Remaining uncertainty |",
            "|---|---|---|---|",
        ]
        for finding in evidence.findings:
            confidence = "—" if finding.confidence is None else f"{finding.confidence:.2f}"
            lines.append(
                f"| {_cell(finding.step)} | {_cell(finding.summary)} | {confidence} | "
                f"{_cell(finding.uncertainty or '—')} |"
            )
        lines.append("")
    else:
        lines += ["No structured findings were recorded.", ""]
    lines += ["## Feature coverage", ""]
    if evidence.features:
        lines += ["| Feature | Status | Scenarios |", "|---|---|---|"]
        for feature in evidence.features:
            status = (
                "covered"
                if feature.get("passed")
                else "failed"
                if feature.get("covered")
                else "not covered"
            )
            scenarios = ", ".join(str(item) for item in feature.get("scenarios") or []) or "-"
            lines.append(
                f"| {_cell(feature.get('name') or feature.get('id') or '?')} | {status} | "
                f"{_cell(scenarios)} |"
            )
        lines.append("")
    else:
        lines += ["No feature map was recorded for this proof.", ""]
    lines += ["## Artifacts", ""]
    if evidence.artifacts:
        lines += ["| Kind | File | SHA-256 |", "|---|---|---|"]
        lines += [
            f"| {_cell(item.kind)} | `{_cell(item.path)}` | `{item.sha256[:12]}` |"
            for item in evidence.artifacts
        ]
        lines.append("")
    else:
        lines += ["No runtime artifacts were attached.", ""]
    lines += ["## Memory recall", ""]
    if evidence.memory_recall:
        lines += [f"- {_cell(item)}" for item in evidence.memory_recall]
        lines.append("")
    else:
        lines += ["No memory recall was recorded.", ""]
    lines += ["## Challenge", ""]
    if evidence.challenge is None:
        lines += ["No independent challenge was run.", ""]
    else:
        decision = "ALLOW" if evidence.challenge.allow else "BLOCK"
        lines += [f"**{decision}** — {_cell(evidence.challenge.reason or 'no reason')}.", ""]
        if evidence.challenge.concerns:
            lines += ["| Concern |", "|---|"]
            lines += [f"| {_cell(item)} |" for item in evidence.challenge.concerns]
            lines.append("")
        lines += [
            f"Model `{evidence.challenge.model}` · provider `{evidence.challenge.provider}` · "
            f"prompt `{evidence.challenge.prompt_sha256 or '—'}`.",
            "",
        ]
    lines += ["## Residual risk", ""]
    if evidence.not_tested:
        lines += [f"- Not tested: `{_cell(item)}`" for item in evidence.not_tested]
    else:
        lines.append("- Not tested: none recorded.")
    if evidence.would_block:
        lines += [f"- Observe mode would block: `{_cell(item)}`" for item in evidence.would_block]
    if not evidence.policy.ok:
        lines.append("- Policy violations block this change.")
    if evidence.verdict is None:
        lines.append("- No verdict: the change was not judged.")
    lines.append("")
    lines += ["## Commands", ""]
    commands = [
        command
        for command in (evidence.reproduce, evidence.test, evidence.preview)
        if command is not None
    ]
    if not commands:
        lines += ["Not attempted.", ""]
    else:
        lines += [
            "| Step | Command | Exit | Duration (ms) | Output SHA-256 |",
            "|---|---|---|---|---|",
        ]
        for command in commands:
            lines.append(
                f"| {_cell(command.step)} | `{_cell(' '.join(command.argv))}` | "
                f"{command.exit_code} | {command.duration_ms} | `{command.output_sha256}` |"
            )
        lines += [
            "",
            "_Reproduction must fail on the base commit; the test step must pass "
            "after the change._",
            "",
        ]
    lines += ["## Change", ""]
    if evidence.diff_stat:
        lines += ["| File | + | - |", "|---|---|---|"]
        for row in evidence.diff_stat:
            added = "binary" if row.added < 0 else str(row.added)
            removed = "binary" if row.removed < 0 else str(row.removed)
            lines.append(f"| `{_cell(row.path)}` | {added} | {removed} |")
        lines.append("")
        lines.append(f"Files changed: **{len(evidence.files_changed)}**.")
    else:
        lines.append("No change was produced.")
    lines.append("")
    lines += ["## Policy", ""]
    if evidence.policy.ok:
        lines.append("No violations.")
    else:
        lines += ["| Path | Reason |", "|---|---|"]
        for violation in evidence.policy.violations:
            lines.append(f"| `{_cell(violation.path)}` | {_cell(violation.reason)} |")
    lines.append("")
    lines += [
        "## Cost",
        "",
        f"- tokens: `{evidence.tokens}`",
        f"- usd: `{evidence.usd:.4f}`",
        f"- wall: `{evidence.duration_ms} ms`",
        f"- model: `{evidence.model or '—'}` · provider: `{evidence.provider or '—'}`",
        f"- prompt: `{evidence.prompt_name or '—'}` · sha256: `{evidence.prompt_sha256 or '—'}`",
        "",
    ]
    if evidence.diff.strip():
        diff = evidence.diff
        truncated = len(diff) > MAX_DIFF_CHARS
        shown = diff[:MAX_DIFF_CHARS]
        lines += ["## Diff", "", "```diff", shown.rstrip("\n"), "```", ""]
        if truncated:
            lines += ["_Diff truncated; the full diff is in `evidence.json`._", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_evidence(directory: Path, evidence: Evidence) -> tuple[Path, Path]:
    bound = evidence.bind() if not evidence.proof_sha256 else evidence
    json_path = directory / "evidence.json"
    md_path = directory / "evidence.md"
    json_path.write_text(bound.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(bound), encoding="utf-8", newline="\n")
    return json_path, md_path


def violations_report(violations: list[Violation]) -> PolicyReport:
    return PolicyReport(ok=not violations, violations=violations)


def priority_order(priority: Priority) -> int:
    return 0 if priority is Priority.P0 else 1
