"""A real model-backed assistant over one recorded run.

The model runs in agent-core's Python through a subprocess worker, so Works keeps its own small
dependency tree. Answers are advisory: they never approve, release, retry or change a task. Every
answer is stored as a `thread.agent` event, so the worklog stays auditable.
"""

from __future__ import annotations

import json
import subprocess  # nosec B404
from collections.abc import Iterator
from typing import Any

from works.adapters.queue.store import Queue
from works.application.assistant.context import (
    build_context,
)
from works.application.assistant.context import (
    payload as _payload,
)
from works.application.assistant.runtime import (
    DEFAULT_BASE,
    DEFAULT_MODEL,
    WORKER,
    agent_core,
    agent_python,
    availability,
)
from works.application.assistant.runtime import (
    command as _command,
)
from works.application.assistant.runtime import (
    environment as _environment,
)
from works.config.paths import WorksPaths
from works.domain.errors import ConfigError

STANCES = {"support", "concern", "block"}


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


def _collect(payload: dict[str, Any], noun: str = "answer") -> dict[str, Any]:
    """Run the worker once and return the final `done` event."""
    completed = subprocess.run(  # nosec B603
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
            f"Mira returned no {noun}: {detail[-1] if detail else completed.returncode}"
        )
    return answer


def ask_mira(paths: WorksPaths, task_id: str, question: str) -> dict[str, Any]:
    answer = _collect(_payload(paths, task_id, question, stream=False))
    _record(paths, task_id, question, answer)
    return answer


def _generate_messages(
    paths: WorksPaths,
    task_id: str,
    *,
    kind: str,
    roles: tuple[str, ...],
    noun: str,
) -> list[dict[str, Any]]:
    """Ask the model for role messages and record each as an advisory thread event.

    Model text is stored with `generated: true`; it never becomes evidence and cannot change a
    verdict, a gate or a task state.
    """
    answer = _collect(
        {
            "kind": kind,
            "context": build_context(paths, task_id),
            "stream": False,
        },
        noun,
    )
    raw_messages = answer.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ConfigError(f"Mira returned no {noun} messages")
    queue = Queue(paths)
    recorded: list[dict[str, Any]] = []
    for index, item in enumerate(raw_messages[:3]):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        if role not in roles or not text:
            continue
        data = {
            "role": role,
            "text": text[:1200],
            "model": answer.get("model") or "",
            "tokens": int(answer.get("tokens") or 0) if index == 0 else 0,
            "usd": float(answer.get("usd") or 0.0) if index == 0 else 0.0,
            "by": "mira",
            "generated": True,
        }
        if kind == "discussion":
            stance = str(item.get("stance") or "").strip().lower()
            if stance in STANCES:
                data["stance"] = stance
        queue.append(task_id, f"thread.{kind}", data)
        recorded.append(data)
    if not recorded:
        raise ConfigError(f"Mira returned no usable {noun}")
    return recorded


def generate_commentary(paths: WorksPaths, task_id: str) -> list[dict[str, Any]]:
    """Generate three short advisory messages from the recorded run.

    The model writes commentary, never evidence. Each message is stored as `thread.commentary`
    with `generated: true`, so the UI can mark it as model output.
    """
    return _generate_messages(
        paths,
        task_id,
        kind="commentary",
        roles=("builder", "inspector", "reporter"),
        noun="commentary",
    )


def generate_discussion(paths: WorksPaths, task_id: str) -> list[dict[str, Any]]:
    """Generate an advisory inspector/challenger/reporter discussion.

    Each message carries an optional stance and is stored as `thread.discussion` with
    `generated: true`. The discussion is labelled AI text and cannot change the verdict or a gate.
    """
    return _generate_messages(
        paths,
        task_id,
        kind="discussion",
        roles=("inspector", "challenger", "reporter"),
        noun="discussion",
    )


def ask_mira_stream(paths: WorksPaths, task_id: str, question: str) -> Iterator[dict[str, Any]]:
    payload = _payload(paths, task_id, question, stream=True)
    process = subprocess.Popen(  # nosec B603
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


__all__ = [
    "DEFAULT_BASE",
    "DEFAULT_MODEL",
    "STANCES",
    "WORKER",
    "agent_core",
    "agent_python",
    "ask_mira",
    "ask_mira_stream",
    "availability",
    "build_context",
    "generate_commentary",
    "generate_discussion",
]
