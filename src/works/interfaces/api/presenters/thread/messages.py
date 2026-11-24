"""One thread message per event kind.

Each handler returns only the fields it changes; the dispatcher fills the rest and
drops unknown events so the session view stays quiet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from works.domain.records import Event, Task

Fields = dict[str, Any]


def _created(event: Event, task: Task) -> Fields:
    role = {
        "manual": "person",
        "tracker": "tracker",
        "detector": "monitor",
    }.get(task.source.kind.value, "person")
    return {
        "role": role,
        "title": "Reported",
        "body": task.source.title,
        "facts": [f"{task.source.kind.value}:{task.source.ref}", task.product],
    }


def _plan_drafted(event: Event, task: Task) -> Fields:
    data = event.data
    summary = str(data.get("summary") or "A plan for the flow and its must-pass scenarios.")
    ids = data.get("scenario_ids") or []
    p0 = data.get("p0") or []
    p1 = data.get("p1") or []
    provenance = data.get("provenance") or {}
    validation = data.get("validation") or {}
    nodes = data.get("nodes") or []
    plan_id = str(data.get("plan_id") or "unversioned")
    plan_hash = str(data.get("hash") or "")
    planner = str(provenance.get("planner") or "deterministic")
    model = provenance.get("model")
    rows = [
        ["Plan", plan_id],
        ["Steps", " -> ".join(nodes)],
        ["Scenarios", f"{len(ids)} ({len(p0)} P0 / {len(p1)} P1)"],
        ["Planner", f"{planner}" + (f" / {model}" if model else "")],
        ["Lint", "ok" if validation.get("ok") else "failed"],
    ]
    if plan_hash:
        rows.append(["Hash", plan_hash[:12]])
    tokens = int(provenance.get("tokens") or 0)
    usd = float(provenance.get("usd") or 0.0)
    rows.append(
        [
            "Planner cost",
            f"{tokens} tokens / ${usd:.4f}" if tokens else "not reported",
        ]
    )
    for warning in (validation.get("warnings") or [])[:3]:
        rows.append(["Warning", str(warning)])
    approve = {
        "label": "Approve plan",
        "action": "approve-plan",
        "tone": "primary",
        "recommended": True,
    }
    return {
        "role": "builder",
        "title": "Plan drafted",
        "body": summary if len(summary) <= 280 else summary[:277].rstrip() + "...",
        "facts": [
            plan_id,
            f"{len(nodes)} step(s)",
            f"{len(ids)} scenario(s)",
            f"{len(p0)} P0",
            f"{len(p1)} P1",
        ],
        "card": {
            "kind": "question",
            "prompt": "Review the plan, then approve it or open the run.",
            "rows": rows,
            "options": (
                [approve, {"label": "Open run", "action": "open-run"}]
                if task.state.value == "planning"
                else [{"label": "Open run", "action": "open-run"}]
            ),
        },
    }


def _plan_deviation(event: Event, task: Task) -> Fields:
    data = event.data
    deviations = data.get("deviations") or []
    return {
        "role": "system",
        "title": "Plan drift",
        "body": "The builder touched paths outside the plan's named write scope.",
        "facts": [f"plan {data.get('plan_id', '?')}", *[str(item) for item in deviations]],
        "card": {
            "kind": "question",
            "prompt": "Visible drift is not a failure, but the proof now records it.",
            "rows": [["Unplanned", ", ".join(str(item) for item in deviations)]],
            "options": [{"label": "Open evidence", "action": "open-evidence"}],
        },
    }


def _gate_decided(event: Event, task: Task) -> Fields:
    data = event.data
    gate = str(data.get("gate") or "gate")
    facts = [f"commit {str(data.get('commit', '—'))[:12]}"]
    if data.get("proof_sha256"):
        facts.append(f"proof {str(data['proof_sha256'])[:12]}")
    return {
        "role": "person",
        "title": "Plan approved" if gate == "plan" else "Release approved",
        "body": f"{data.get('by', 'a person')} opened the {gate} gate.",
        "facts": facts,
        "tone": "ok",
        "card": {
            "kind": "gate",
            "rows": [
                ["Gate", gate],
                ["Decision", str(data.get("decision", "approved"))],
                ["By", str(data.get("by", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
            ],
        },
    }


def _attempt_started(event: Event, task: Task) -> Fields:
    return {
        "role": "builder",
        "title": f"Build attempt {event.data.get('attempt', '?')} started",
        "body": "The builder is editing the disposable worktree.",
    }


def _step_finished(event: Event, task: Task) -> Fields:
    data = event.data
    step = str(data.get("step") or "step")
    code = data.get("exit_code", "?")
    role = "verifier" if step in ("reproduce", "test", "preview", "check") else "builder"
    if step == "reproduce":
        title = "Reproduction confirmed" if code != 0 else "Reproduction did not fail"
        body = (
            "The failing check failed on the base commit, as expected."
            if code != 0
            else "The check passed on the base commit, so the bug was not reproduced."
        )
        tone = "ok" if code != 0 else "bad"
    elif step == "test":
        title = "Tests passed" if code == 0 else "Tests failed"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    elif step == "preview":
        title = "Preview passed" if code == 0 else "Preview failed"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    else:
        title = f"{step.capitalize()} finished"
        body = f"Exit code {code}."
        tone = "ok" if code == 0 else "bad"
    return {
        "role": role,
        "title": title,
        "body": body,
        "facts": [step],
        "tone": tone,
    }


def _challenge_decided(event: Event, task: Task) -> Fields:
    data = event.data
    allow = bool(data.get("allow"))
    return {
        "role": "challenger",
        "title": "Independent check allowed" if allow else "Independent check blocked",
        "body": str(data.get("reason") or "No reason recorded."),
        "facts": [f"concerns {len(data.get('concerns') or [])}"],
        "tone": "ok" if allow else "bad",
        "card": {
            "kind": "challenge",
            "rows": [["Allow", "yes" if allow else "no"], ["Model", str(data.get("model", "—"))]],
        },
    }


def _risk_rated(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Risk: {data.get('level', 'unknown')}",
        "body": "; ".join(str(item) for item in (data.get("reasons") or []))
        or "No reasons recorded.",
        "facts": [f"owners {', '.join(data.get('owners') or []) or 'none'}"],
    }


def _decision_made(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Decision: {data.get('verb', '—')}",
        "body": str(data.get("reason_code") or ""),
        "facts": [f"gate {data.get('gate', '—')}"],
    }


def _finding(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Finding recorded",
        "body": str(data.get("summary") or ""),
        "facts": [f"step {data.get('step', '—')}", f"confidence {data.get('confidence', '—')}"],
        "tone": "bad",
    }


def _flake(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Flaky test recorded",
        "body": f"{data.get('scenario_id', '?')} has an owner and an expiry.",
        "facts": [f"owner {data.get('owner', '—')}"],
        "tone": "bad",
    }


def _would_block(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Observe mode would block",
        "body": f"{data.get('gate', '—')}: {data.get('reason', '')}",
        "tone": "bad",
    }


def _readiness(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": f"Readiness: {data.get('status', '—')}",
        "body": f"{data.get('passed', '?')} of {data.get('total', '?')} checks passed.",
        "facts": [str(data.get("note") or "")],
        "tone": "ok" if data.get("status") == "pass" else "bad",
    }


def _team_verified(event: Event, task: Task) -> Fields:
    data = event.data
    verdict = str(data.get("verdict") or "?")
    blockers = data.get("blockers") or []
    inspector = data.get("inspector") or {}
    challenger = data.get("challenger") or {}
    inspector_text = (
        ("allow" if inspector.get("allow") else "block") if inspector else "not recorded"
    )
    challenger_text = (
        ("allow" if challenger.get("allow") else "block") if challenger else "not recorded"
    )
    return {
        "role": "team",
        "title": f"Team verdict: {verdict}",
        "body": "; ".join(str(item) for item in blockers) or "No blockers.",
        "facts": [f"inspector {inspector_text}", f"challenger {challenger_text}"],
        "tone": "ok" if verdict == "allow" else "bad",
        "card": {
            "kind": "team",
            "rows": [
                ["Verdict", verdict],
                ["Inspector", inspector_text],
                ["Challenger", challenger_text],
            ],
        },
    }


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


def _agent(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "mira",
        "title": "Mira answered",
        "body": str(data.get("answer") or ""),
        "facts": [
            f"model {data.get('model') or '-'}",
            f"{data.get('tokens') or 0} token(s)",
        ],
        "generated": True,
        "generated_label": "AI answer",
        "card": {
            "kind": "question",
            "rows": [["Question", str(data.get("question") or "")]],
        },
    }


def _commentary(event: Event, task: Task) -> Fields:
    data = event.data
    role = str(data.get("role") or "mira")
    return {
        "role": role,
        "title": {
            "builder": "Builder commentary",
            "inspector": "Inspector commentary",
            "reporter": "Reporter commentary",
        }.get(role, "Mira commentary"),
        "body": str(data.get("text") or ""),
        "facts": ["AI commentary", f"model {data.get('model') or '-'}"],
        "generated": True,
        "generated_label": "AI commentary",
    }


def _discussion(event: Event, task: Task) -> Fields:
    data = event.data
    role = str(data.get("role") or "mira")
    return {
        "role": role,
        "title": {
            "inspector": "Inspector discusses",
            "challenger": "Challenger discusses",
            "reporter": "Reporter discusses",
        }.get(role, "Team discussion"),
        "body": str(data.get("text") or ""),
        "stance": str(data.get("stance") or ""),
        "facts": ["AI discussion", f"model {data.get('model') or '-'}"],
        "generated": True,
        "generated_label": "AI discussion",
    }


def _thread_note(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "person",
        "title": "Context added",
        "body": str(data.get("message") or ""),
        "facts": [f"by {data.get('by', 'a person')}"],
    }


def _note(event: Event, task: Task) -> Fields:
    data = event.data
    raw_body = str(data.get("message") or "")
    if data.get("model"):
        paths = data.get("paths") or []
        return {
            "role": "builder",
            "title": "Proposal received",
            "body": f"{data.get('model')} proposed a change to {len(paths)} file(s).",
            "facts": [str(item) for item in paths],
        }
    if "v0" in raw_body and "release gate" in raw_body:
        options: list[dict[str, Any]] = [{"label": "Open run", "action": "open-run"}]
        if task.state.value == "proved":
            options.insert(
                0,
                {
                    "label": "Release this commit",
                    "action": "release",
                    "tone": "primary",
                    "recommended": True,
                },
            )
        options.insert(1, {"label": "Open release", "action": "open-release"})
        return {
            "role": "system",
            "title": "Proof ready",
            "body": "proof is ready; gate 2 is the next step",
            "card": {
                "kind": "question",
                "prompt": "Release this commit?",
                "options": options,
            },
        }
    return {"role": "system", "title": "Note", "body": raw_body}


def _shadow(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": "LAIX shadow decision",
        "body": f"{data.get('gate', 'gate')}: {data.get('reason_code', '')}",
        "facts": [f"agree {data.get('agree', '—')}"],
    }


def _wait(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": {
            "wait.started": "Waiting",
            "wait.woken": "Woke up",
            "wait.expired": "Wait expired",
        }[event.type],
        "body": str(data.get("wake_on") or data.get("on") or ""),
    }


def _memory(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "system",
        "title": {
            "memory.reported": "PPMA synced",
            "memory.failed": "PPMA failed",
            "memory.recalled": "Memory recall",
            "memory.recall_failed": "Memory recall failed",
        }.get(event.type, "Memory"),
        "body": str(data.get("error") or data.get("via") or ""),
        "facts": [f"{len(data.get('statements') or [])} statement(s)"],
        "tone": "bad" if event.type.endswith("failed") else "",
    }


def _state_changed(event: Event, task: Task) -> Fields | None:
    data = event.data
    target = str(data.get("to") or "")
    if target not in ("blocked", "released", "reverted"):
        return None
    return {
        "role": "system",
        "title": f"State: {target}",
        "body": str(data.get("reason") or ""),
        "tone": "bad" if target in ("blocked", "reverted") else "ok",
    }


def _preview(event: Event, task: Task) -> Fields:
    data = event.data
    return {
        "role": "verifier",
        "title": "Preview finished",
        "body": f"Exit code {data.get('exit_code', '?')}.",
        "tone": "ok" if data.get("exit_code") == 0 else "bad",
    }


Handler = Callable[[Event, Task], "Fields | None"]

_HANDLERS: dict[str, Handler] = {
    "task.created": _created,
    "plan.drafted": _plan_drafted,
    "plan.deviation": _plan_deviation,
    "gate.decided": _gate_decided,
    "attempt.started": _attempt_started,
    "step.finished": _step_finished,
    "challenge.decided": _challenge_decided,
    "risk.rated": _risk_rated,
    "decision.made": _decision_made,
    "decision.shadow": _shadow,
    "finding": _finding,
    "flake": _flake,
    "would_block": _would_block,
    "readiness.checked": _readiness,
    "team.verified": _team_verified,
    "delivery.finished": _delivery_finished,
    "confirmation.finished": _confirmation_finished,
    "deploy.finished": _deploy_finished,
    "escape.detected": _escape,
    "rework.detected": _rework,
    "thread.agent": _agent,
    "thread.commentary": _commentary,
    "thread.discussion": _discussion,
    "thread.note": _thread_note,
    "note": _note,
    "wait.started": _wait,
    "wait.woken": _wait,
    "wait.expired": _wait,
    "state.changed": _state_changed,
    "preview.finished": _preview,
}
_PREFIX_HANDLERS: tuple[tuple[str, Handler], ...] = (("memory.", _memory),)


def _thread_message(event: Event, task: Task) -> dict[str, Any] | None:
    handler = _HANDLERS.get(event.type)
    if handler is None:
        for prefix, candidate in _PREFIX_HANDLERS:
            if event.type.startswith(prefix):
                handler = candidate
                break
    if handler is None:
        return None
    fields = handler(event, task)
    if fields is None:
        return None
    return {
        "seq": event.seq,
        "at": event.ts.isoformat(),
        "role": fields.get("role", "system"),
        "type": event.type,
        "title": fields.get("title", event.type),
        "body": fields.get("body", ""),
        "facts": [item for item in (fields.get("facts") or []) if item],
        "tone": fields.get("tone", ""),
        "generated": bool(event.data.get("generated")) or bool(fields.get("generated")),
        "generated_label": fields.get("generated_label", ""),
        "stance": fields.get("stance", ""),
        "card": fields.get("card"),
    }
