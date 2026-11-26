"""A plain-language summary of one evidence record.

The template is deterministic: every sentence comes from a field the run already recorded. It never
calls a model, never infers a cause and never invents a number. A missing field is named as such.
"""

from __future__ import annotations

import hashlib

from works.domain.evidence.models import Evidence
from works.domain.records import Priority

NOT_RECORDED = "not recorded"
MAX_FINDINGS = 3
MAX_FILES = 10


def summary_digest(text: str) -> str:
    """The digest recorded next to the summary and in its artifact."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(text: str) -> str:
    return " ".join(text.split())


def _verdict(evidence: Evidence) -> list[str]:
    verdict = evidence.verdict
    if verdict is None:
        return ["The verdict was not recorded."]
    lines = [
        f"Verdict: {'allow' if verdict.allow else 'block'}"
        + (f" — {_clean(verdict.reason)}" if verdict.reason else "")
        + "."
    ]
    p0 = [outcome for outcome in verdict.outcomes if outcome.priority is Priority.P0]
    p1 = [outcome for outcome in verdict.outcomes if outcome.priority is Priority.P1]
    if p0:
        passed = sum(1 for outcome in p0 if outcome.passed)
        lines.append(f"Must-pass checks: {passed} of {len(p0)} passed.")
    if p1:
        passed = sum(1 for outcome in p1 if outcome.passed)
        lines.append(f"Supporting checks: {passed} of {len(p1)} passed.")
    return lines


def _changed(evidence: Evidence) -> list[str]:
    stats = evidence.diff_stat
    files = evidence.files_changed
    if stats:
        total = sum(stat.added + stat.removed for stat in stats)
        lines = [f"{len(stats)} file(s), {total} line(s) changed."]
        shown = stats[:MAX_FILES]
        lines.extend(f"- `{stat.path}` (+{stat.added}, -{stat.removed})" for stat in shown)
        if len(stats) > len(shown):
            lines.append(f"- and {len(stats) - len(shown)} more file(s).")
        return lines
    if files:
        lines = [f"{len(files)} file(s) changed; line counts were not recorded."]
        lines.extend(f"- `{path}`" for path in files[:MAX_FILES])
        if len(files) > MAX_FILES:
            lines.append(f"- and {len(files) - MAX_FILES} more file(s).")
        return lines
    return ["No file change was recorded."]


def render_summary(evidence: Evidence) -> str:
    """The five sections a non-engineer needs at the release gate."""
    lines: list[str] = ["## What was wrong", ""]
    if evidence.task_title:
        lines.append(_clean(evidence.task_title) + ".")
    else:
        lines.append("The task title was not recorded.")
    if evidence.reproduction_command:
        lines.append(
            "Reproduced with `"
            + " ".join(evidence.reproduction_command)
            + "`"
            + (f" on `{evidence.base_commit}`" if evidence.base_commit else "")
            + "."
        )
    else:
        lines.append("The reproduction command was not recorded.")
    if evidence.reproduction_hint:
        lines.append(f"The reporter said: {_clean(evidence.reproduction_hint)}")

    lines.extend(["", "## What caused it", ""])
    cause = False
    if evidence.plan_summary:
        lines.append(f"The approved plan described: {_clean(evidence.plan_summary)}")
        cause = True
    findings = [finding.summary for finding in evidence.findings if finding.summary][:MAX_FINDINGS]
    if findings:
        lines.extend(f"- {_clean(finding)}" for finding in findings)
        cause = True
    if not cause:
        lines.append("The cause was not recorded in the plan or the findings.")

    lines.extend(["", "## What changed", ""])
    lines.extend(_changed(evidence))
    if evidence.risk is not None:
        reason = evidence.risk.reasons[0] if evidence.risk.reasons else "no reason recorded"
        lines.append(f"Risk: {evidence.risk.level.value} — {_clean(reason)}.")

    lines.extend(["", "## What proves it", ""])
    lines.extend(_verdict(evidence))
    if evidence.diff_sha256:
        lines.append(f"Diff SHA-256: `{evidence.diff_sha256}`.")
    if evidence.proof_sha256:
        lines.append(f"Proof SHA-256: `{evidence.proof_sha256}`.")
    if evidence.challenge is not None:
        lines.append(
            "Independent review: "
            + ("allow" if evidence.challenge.allow else "block")
            + (f" — {_clean(evidence.challenge.reason)}" if evidence.challenge.reason else "")
            + "."
        )

    lines.extend(["", "## What was not tested", ""])
    if evidence.not_tested:
        lines.extend(f"- {_clean(item)}" for item in evidence.not_tested)
    else:
        lines.append("Nothing was declared untested.")

    return "\n".join(lines).rstrip() + "\n"
