"""The bounded story of a task, as handed to the model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from works.adapters.queue.store import Queue
from works.application.delivery.release import latest_run_dir, release_packet
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError
from works.domain.evidence import Evidence
from works.domain.records import Event, RunRecord


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def build_context(paths: WorksPaths, task_id: str) -> str:
    queue = Queue(paths)
    task = queue.load(task_id)
    events = queue.events(task_id)
    lines = [
        f"Task: {task.id}",
        f"State: {task.state.value}",
        f"Product: {task.product}",
        f"Source: {task.source.kind.value}:{task.source.ref}",
        f"Title: {task.source.title}",
    ]
    run_dir = latest_run_dir(paths, task_id)
    if run_dir is None:
        lines.append("Run: none")
    else:
        record = RunRecord.model_validate_json((run_dir / "run.json").read_text(encoding="utf-8"))
        evidence = Evidence.model_validate_json(
            (run_dir / "evidence.json").read_text(encoding="utf-8")
        )
        lines.extend(
            [
                f"Run: {record.run_id}",
                f"Base commit: {record.base_commit or '-'}",
                f"Proof SHA-256: {evidence.proof_sha256 or '-'}",
                f"Verdict: {'allow' if evidence.verdict and evidence.verdict.allow else 'block'}",
                f"Risk: {evidence.risk.level.value if evidence.risk else '-'}",
                f"Files changed: {', '.join(evidence.files_changed) or '-'}",
                f"Not tested: {', '.join(evidence.not_tested) or 'none recorded'}",
                f"Policy: {'pass' if evidence.policy.ok else 'fail'}",
            ]
        )
        if evidence.verdict is not None:
            outcomes = evidence.verdict.outcomes
            passed = sum(1 for outcome in outcomes if outcome.passed)
            lines.append(f"Scenarios: {passed}/{len(outcomes)} passed")
            failed = [outcome.id for outcome in outcomes if not outcome.passed]
            if failed:
                lines.append("Failed scenarios: " + ", ".join(failed))
            if evidence.verdict.reason:
                lines.append(f"Verdict reason: {evidence.verdict.reason}")
        for step in ("reproduce", "test", "preview"):
            command = getattr(evidence, step)
            if command is not None:
                lines.append(
                    f"Command {step}: exit {command.exit_code} in {command.duration_ms} ms"
                )
        if evidence.challenge is not None:
            lines.append(
                f"Challenge: {'allow' if evidence.challenge.allow else 'block'}"
                f" ({evidence.challenge.reason})"
            )
        plan = next((event.data for event in reversed(events) if event.type == "plan.drafted"), {})
        if plan:
            lines.append(
                f"Plan: {len(plan.get('scenario_ids') or [])} scenario(s); "
                f"P0={len(plan.get('p0') or [])}; P1={len(plan.get('p1') or [])}"
            )
        release = release_packet(paths, task_id).as_dict()
        lines.append(f"Release: {'released' if release.get('released') else 'not released'}")
        if release.get("blockers"):
            lines.append("Release blockers: " + "; ".join(release["blockers"]))
    delivery = load_json(run_dir / "delivery.json") if run_dir is not None else None
    confirmation = load_json(run_dir / "confirmation.json") if run_dir is not None else None
    if delivery:
        lines.append(
            f"Delivery: {delivery.get('branch', '-')} at {str(delivery.get('commit', '-'))[:12]}; "
            f"PR={delivery.get('pr_url') or '-'}; comment={delivery.get('comment_url') or '-'}"
        )
    if confirmation:
        lines.append(
            f"Confirmation: {'pass' if confirmation.get('ok') else 'fail'}; "
            f"target={confirmation.get('target', '-')}"
        )
    team_latest: dict[str, Any] | None = None
    for event in events:
        if event.type == "team.verified":
            team_latest = dict(event.data)
    if team_latest is not None:
        lines.append(
            f"Team verdict: {team_latest.get('verdict', '-')}; "
            f"blockers={', '.join(team_latest.get('blockers') or []) or 'none'}"
        )
    thread = [
        f"- {event.type}: {json.dumps(event.data, ensure_ascii=False)[:500]}"
        for event in events[-15:]
        if event.type in ("thread.note", "thread.agent")
    ]
    if thread:
        lines.append("Recent worklog messages:\n" + "\n".join(thread))
    return "\n".join(lines)[:12000]


def history(events: list[Event], *, limit: int = 6) -> list[dict[str, str]]:
    """Recent Ask Mira turns, so a follow-up question has the earlier answer in view."""
    items: list[dict[str, str]] = []
    for event in events:
        if event.type != "thread.agent":
            continue
        question = str(event.data.get("question") or "").strip()
        answer = str(event.data.get("answer") or "").strip()
        if not question or not answer:
            continue
        items.append({"role": "user", "content": question[:2000]})
        items.append({"role": "assistant", "content": answer[:4000]})
    return items[-limit:]


def payload(paths: WorksPaths, task_id: str, question: str, *, stream: bool) -> dict[str, Any]:
    clean = question.strip()
    if not clean:
        raise ConfigError("question is required")
    if len(clean) > 2000:
        raise ConfigError("question is too long")
    return {
        "question": clean,
        "context": build_context(paths, task_id),
        "stream": stream,
        "history": history(Queue(paths).events(task_id)),
    }
