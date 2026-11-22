"""A real model-backed assistant over one recorded run.

The model runs in agent-core's Python through a subprocess worker, so Works keeps its own small
dependency tree. Answers are advisory: they never approve, release, retry or change a task. Every
answer is stored as a `thread.agent` event, so the worklog stays auditable.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import WorksPaths
from .errors import ConfigError
from .evidence import Evidence
from .queue import Queue
from .records import RunRecord
from .release import latest_run_dir, release_packet

WORKER = Path(__file__).resolve().parents[2] / "scripts" / "agent_chat_worker.py"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE = "https://api.deepseek.com/anthropic"


def agent_python() -> Path:
    return Path(
        os.environ.get("WORKS_AGENT_PYTHON")
        or r"C:\Workspace\openjiuwen\agent-core\.venv\Scripts\python.exe"
    )


def agent_core() -> Path:
    return Path(os.environ.get("WORKS_AGENT_CORE") or r"C:\Workspace\openjiuwen\agent-core")


def availability() -> dict[str, Any]:
    key = os.environ.get("WORKS_MODEL_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    python = agent_python()
    core = agent_core()
    available = bool(key) and python.exists() and core.exists() and WORKER.exists()
    reason = ""
    if not key:
        reason = "no model key: set ANTHROPIC_API_KEY or WORKS_MODEL_KEY"
    elif not python.exists():
        reason = f"agent-core Python not found: {python}"
    elif not core.exists():
        reason = f"agent-core checkout not found: {core}"
    elif not WORKER.exists():
        reason = "agent chat worker not found"
    return {
        "available": available,
        "reason": reason,
        "model": os.environ.get("WORKS_AGENT_MODEL") or DEFAULT_MODEL,
        "base": os.environ.get("WORKS_MODEL_BASE") or DEFAULT_BASE,
    }


def _load(path: Path) -> dict[str, Any] | None:
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
    delivery = _load(run_dir / "delivery.json") if run_dir is not None else None
    confirmation = _load(run_dir / "confirmation.json") if run_dir is not None else None
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


def _payload(paths: WorksPaths, task_id: str, question: str, *, stream: bool) -> dict[str, Any]:
    clean = question.strip()
    if not clean:
        raise ConfigError("question is required")
    if len(clean) > 2000:
        raise ConfigError("question is too long")
    return {
        "question": clean,
        "context": build_context(paths, task_id),
        "stream": stream,
        "history": [],
    }


def _command() -> list[str]:
    state = availability()
    if not state["available"]:
        raise ConfigError(f"Mira is not available: {state['reason']}")
    return [str(agent_python()), str(WORKER)]


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[1]), str(agent_core()), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    env.setdefault("WORKS_AGENT_MODEL", DEFAULT_MODEL)
    env.setdefault("WORKS_MODEL_BASE", DEFAULT_BASE)
    return env


def _record(paths: WorksPaths, task_id: str, question: str, answer: dict[str, Any]) -> None:
    Queue(paths).append(
        task_id,
        "thread.agent",
        {
            "question": question,
            "answer": answer.get("text") or answer.get("answer") or "",
            "model": answer.get("model") or "",
            "tokens": int(answer.get("tokens") or 0),
            "usd": float(answer.get("usd") or 0.0),
            "by": "mira",
        },
    )


def ask_mira(paths: WorksPaths, task_id: str, question: str) -> dict[str, Any]:
    payload = _payload(paths, task_id, question, stream=False)
    completed = subprocess.run(  # noqa: S603  # nosec B603
        _command(),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=_environment(),
        timeout=180,
        check=False,
    )
    answer: dict[str, Any] | None = None
    for line in completed.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            raise ConfigError(f"Mira failed: {event.get('error')}")
        if event.get("type") == "done":
            answer = event
    if answer is None:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        raise ConfigError(
            f"Mira returned no answer: {detail[-1] if detail else completed.returncode}"
        )
    _record(paths, task_id, question, answer)
    return answer


def ask_mira_stream(paths: WorksPaths, task_id: str, question: str) -> Iterator[dict[str, Any]]:
    payload = _payload(paths, task_id, question, stream=True)
    process = subprocess.Popen(  # noqa: S603  # nosec B603
        _command(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_environment(),
    )
    answer: dict[str, Any] | None = None
    parts: list[str] = []
    try:
        if process.stdin is None or process.stdout is None:
            raise ConfigError("Mira worker did not expose its pipes")
        process.stdin.write(json.dumps(payload))
        process.stdin.close()
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "delta":
                parts.append(str(event.get("text") or ""))
                yield event
            elif event.get("type") == "error":
                raise ConfigError(f"Mira failed: {event.get('error')}")
            elif event.get("type") == "done":
                answer = event
                break
        process.wait(timeout=30)
    finally:
        if process.poll() is None:
            process.kill()
    if answer is None:
        raise ConfigError("Mira returned no answer")
    if not answer.get("text"):
        answer["text"] = "".join(parts)
    _record(paths, task_id, question, answer)
    yield {
        "type": "done",
        "text": answer.get("text") or "".join(parts),
        "model": answer.get("model") or "",
        "tokens": int(answer.get("tokens") or 0),
        "usd": float(answer.get("usd") or 0.0),
        "recorded": True,
    }
