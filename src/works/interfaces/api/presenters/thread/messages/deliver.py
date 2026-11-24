"""Thread message handlers: delivery, deployment, confirmation and escapes."""

from __future__ import annotations

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


def _delivery_finished(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "delivery",
        "title": "Delivered",
        "body": f"{data.get('branch', '?')} · {str(data.get('commit', '?'))[:12]}",
        "facts": [str(data.get("provider") or "none"), str(data.get("tracker") or "none")],
        "tone": "ok" if data.get("pushed") else "",
        "card": {
            "kind": "delivery",
            "rows": [
                ["Branch", str(data.get("branch", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
                ["Pull request", str(data.get("pr_url") or "—")],
                ["Comment", str(data.get("comment_url") or "—")],
            ],
        },
    }


def _confirmation_finished(event: Event, task: Task) -> Fields:
    data = event.data
    ok = bool(data.get("ok"))
    return {
        "role": "confirmation",
        "title": "Confirmation passed" if ok else "Confirmation failed",
        "body": str(data.get("target") or "—"),
        "facts": [
            f"exit {data.get('exit_code', '?')}",
            f"proof {str(data.get('output_sha256') or '')[:10]}",
        ],
        "tone": "ok" if ok else "bad",
        "card": {
            "kind": "confirmation",
            "rows": [
                ["Result", "pass" if ok else "fail"],
                ["Target", str(data.get("target", "—"))],
                ["Output SHA", str(data.get("output_sha256", "—"))[:12]],
            ],
        },
    }


def _deploy_finished(event: Event, task: Task) -> Fields:
    data = event.data
    status = str(data.get("status") or "unknown")
    return {
        "role": "delivery",
        "title": {
            "deployed": "Deployed",
            "failed": "Deployment failed",
            "dry_run": "Deployment dry run",
        }.get(status, f"Deployment: {status}"),
        "body": f"{data.get('environment', '?')} · {str(data.get('commit', '?'))[:12]}",
        "facts": [f"exit {data.get('exit_code', '?')}", status],
        "tone": "ok" if status == "deployed" else "bad",
        "card": {
            "kind": "deploy",
            "rows": [
                ["Environment", str(data.get("environment", "-"))],
                ["Commit", str(data.get("commit", "-"))[:12]],
                ["Status", status],
            ],
        },
    }


def _escape(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Escape detected",
        "body": str(data.get("subject") or "A released change came back."),
        "facts": [str(data.get("kind") or "escape"), str(data.get("evidence_commit", ""))[:12]],
        "tone": "bad",
    }


def _rework(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Rework detected",
        "body": str(data.get("reason") or "A later task repeats the same source."),
        "facts": [f"after {data.get('previous_task_id', '?')}"],
        "tone": "bad",
    }
