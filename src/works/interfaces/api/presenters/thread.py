"""HTTP API presenters and runtime helpers."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task


def _thread_message(event: Event, task: Task) -> dict[str, Any] | None:
    data = event.data
    kind = event.type
    role = "system"
    title = kind
    body = ""
    facts: list[str] = []
    tone = ""
    card: dict[str, Any] | None = None
    generated_label = ""
    generated = False
    stance = ""

    if kind == "task.created":
        role = {
            "manual": "person",
            "tracker": "tracker",
            "detector": "monitor",
        }.get(task.source.kind.value, "person")
        title = "Reported"
        body = task.source.title
        facts = [f"{task.source.kind.value}:{task.source.ref}", task.product]
    elif kind == "plan.drafted":
        role = "builder"
        title = "Plan drafted"
        summary = str(data.get("summary") or "A plan for the flow and its must-pass scenarios.")
        body = summary if len(summary) <= 280 else summary[:277].rstrip() + "..."
        ids = data.get("scenario_ids") or []
        p0 = data.get("p0") or []
        p1 = data.get("p1") or []
        provenance = data.get("provenance") or {}
        validation = data.get("validation") or {}
        nodes = data.get("nodes") or []
        plan_id = str(data.get("plan_id") or "unversioned")
        plan_hash = str(data.get("hash") or "")
        facts = [
            plan_id,
            f"{len(nodes)} step(s)",
            f"{len(ids)} scenario(s)",
            f"{len(p0)} P0",
            f"{len(p1)} P1",
        ]
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
        card = {
            "kind": "question",
            "prompt": "Review the plan, then approve it or open the run.",
            "rows": rows,
            "options": (
                [
                    {
                        "label": "Approve plan",
                        "action": "approve-plan",
                        "tone": "primary",
                        "recommended": True,
                    },
                    {"label": "Open run", "action": "open-run"},
                ]
                if task.state.value == "planning"
                else [{"label": "Open run", "action": "open-run"}]
            ),
        }
    elif kind == "plan.deviation":
        role = "system"
        title = "Plan drift"
        deviations = data.get("deviations") or []
        body = "The builder touched paths outside the plan's named write scope."
        facts = [f"plan {data.get('plan_id', '?')}", *[str(item) for item in deviations]]
        card = {
            "kind": "question",
            "prompt": "Visible drift is not a failure, but the proof now records it.",
            "rows": [["Unplanned", ", ".join(str(item) for item in deviations)]],
            "options": [{"label": "Open evidence", "action": "open-evidence"}],
        }
    elif kind == "gate.decided":
        role = "person"
        gate = str(data.get("gate") or "gate")
        title = "Plan approved" if gate == "plan" else "Release approved"
        body = f"{data.get('by', 'a person')} opened the {gate} gate."
        facts = [f"commit {str(data.get('commit', '—'))[:12]}"]
        if data.get("proof_sha256"):
            facts.append(f"proof {str(data['proof_sha256'])[:12]}")
        card = {
            "kind": "gate",
            "rows": [
                ["Gate", gate],
                ["Decision", str(data.get("decision", "approved"))],
                ["By", str(data.get("by", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
            ],
        }
        tone = "ok"
    elif kind == "attempt.started":
        role = "builder"
        title = f"Build attempt {data.get('attempt', '?')} started"
        body = "The builder is editing the disposable worktree."
    elif kind == "step.finished":
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
        facts = [step]
    elif kind == "challenge.decided":
        role = "challenger"
        allow = bool(data.get("allow"))
        title = "Independent check allowed" if allow else "Independent check blocked"
        body = str(data.get("reason") or "No reason recorded.")
        facts = [f"concerns {len(data.get('concerns') or [])}"]
        card = {
            "kind": "challenge",
            "rows": [["Allow", "yes" if allow else "no"], ["Model", str(data.get("model", "—"))]],
        }
        tone = "ok" if allow else "bad"
    elif kind == "risk.rated":
        role = "verifier"
        title = f"Risk: {data.get('level', 'unknown')}"
        body = (
            "; ".join(str(item) for item in (data.get("reasons") or [])) or "No reasons recorded."
        )
        facts = [f"owners {', '.join(data.get('owners') or []) or 'none'}"]
    elif kind == "decision.made":
        role = "verifier"
        title = f"Decision: {data.get('verb', '—')}"
        body = str(data.get("reason_code") or "")
        facts = [f"gate {data.get('gate', '—')}"]
    elif kind == "finding":
        role = "verifier"
        title = "Finding recorded"
        body = str(data.get("summary") or "")
        facts = [f"step {data.get('step', '—')}", f"confidence {data.get('confidence', '—')}"]
        tone = "bad"
    elif kind == "flake":
        role = "verifier"
        title = "Flaky test recorded"
        body = f"{data.get('scenario_id', '?')} has an owner and an expiry."
        facts = [f"owner {data.get('owner', '—')}"]
        tone = "bad"
    elif kind == "would_block":
        role = "verifier"
        title = "Observe mode would block"
        body = f"{data.get('gate', '—')}: {data.get('reason', '')}"
        tone = "bad"
    elif kind == "readiness.checked":
        role = "verifier"
        title = f"Readiness: {data.get('status', '—')}"
        body = f"{data.get('passed', '?')} of {data.get('total', '?')} checks passed."
        facts = [str(data.get("note") or "")]
        tone = "ok" if data.get("status") == "pass" else "bad"
    elif kind == "team.verified":
        role = "team"
        verdict = str(data.get("verdict") or "?")
        title = f"Team verdict: {verdict}"
        blockers = data.get("blockers") or []
        body = "; ".join(str(item) for item in blockers) or "No blockers."
        inspector = data.get("inspector") or {}
        challenger = data.get("challenger") or {}
        inspector_text = (
            ("allow" if inspector.get("allow") else "block") if inspector else "not recorded"
        )
        challenger_text = (
            ("allow" if challenger.get("allow") else "block") if challenger else "not recorded"
        )
        facts = [f"inspector {inspector_text}", f"challenger {challenger_text}"]
        card = {
            "kind": "team",
            "rows": [
                ["Verdict", verdict],
                ["Inspector", inspector_text],
                ["Challenger", challenger_text],
            ],
        }
        tone = "ok" if verdict == "allow" else "bad"
    elif kind == "delivery.finished":
        role = "delivery"
        title = "Delivered"
        body = f"{data.get('branch', '?')} · {str(data.get('commit', '?'))[:12]}"
        facts = [str(data.get("provider") or "none"), str(data.get("tracker") or "none")]
        card = {
            "kind": "delivery",
            "rows": [
                ["Branch", str(data.get("branch", "—"))],
                ["Commit", str(data.get("commit", "—"))[:12]],
                ["Pull request", str(data.get("pr_url") or "—")],
                ["Comment", str(data.get("comment_url") or "—")],
            ],
        }
        tone = "ok" if data.get("pushed") else ""
    elif kind == "confirmation.finished":
        role = "confirmation"
        ok = bool(data.get("ok"))
        title = "Confirmation passed" if ok else "Confirmation failed"
        body = str(data.get("target") or "—")
        facts = [
            f"exit {data.get('exit_code', '?')}",
            f"proof {str(data.get('output_sha256') or '')[:10]}",
        ]
        card = {
            "kind": "confirmation",
            "rows": [
                ["Result", "pass" if ok else "fail"],
                ["Target", str(data.get("target", "—"))],
                ["Output SHA", str(data.get("output_sha256", "—"))[:12]],
            ],
        }
        tone = "ok" if ok else "bad"
    elif kind == "deploy.finished":
        role = "delivery"
        status = str(data.get("status") or "unknown")
        title = {
            "deployed": "Deployed",
            "failed": "Deployment failed",
            "dry_run": "Deployment dry run",
        }.get(status, f"Deployment: {status}")
        body = f"{data.get('environment', '?')} A� {str(data.get('commit', '?'))[:12]}"
        facts = [f"exit {data.get('exit_code', '?')}", status]
        environment = str(data.get("environment", "-"))
        commit = str(data.get("commit", "-"))[:12]
        card = {
            "kind": "deploy",
            "rows": [
                ["Environment", environment],
                ["Commit", commit],
                ["Status", status],
            ],
        }
        tone = "ok" if status == "deployed" else "bad"
    elif kind == "escape.detected":
        role = "verifier"
        title = "Escape detected"
        body = str(data.get("subject") or "A released change came back.")
        facts = [str(data.get("kind") or "escape"), str(data.get("evidence_commit", ""))[:12]]
        tone = "bad"
    elif kind == "rework.detected":
        role = "verifier"
        title = "Rework detected"
        body = str(data.get("reason") or "A later task repeats the same source.")
        facts = [f"after {data.get('previous_task_id', '?')}"]
        tone = "bad"
    elif kind == "thread.agent":
        role = "mira"
        title = "Mira answered"
        body = str(data.get("answer") or "")
        facts = [
            f"model {data.get('model') or '-'}",
            f"{data.get('tokens') or 0} token(s)",
        ]
        generated_label = "AI answer"
        generated = True
        card = {
            "kind": "question",
            "rows": [["Question", str(data.get("question") or "")]],
        }
    elif kind == "thread.commentary":
        role = str(data.get("role") or "mira")
        title = {
            "builder": "Builder commentary",
            "inspector": "Inspector commentary",
            "reporter": "Reporter commentary",
        }.get(role, "Mira commentary")
        body = str(data.get("text") or "")
        facts = ["AI commentary", f"model {data.get('model') or '-'}"]
        generated_label = "AI commentary"
        generated = True
        card = None
    elif kind == "thread.discussion":
        role = str(data.get("role") or "mira")
        title = {
            "inspector": "Inspector discusses",
            "challenger": "Challenger discusses",
            "reporter": "Reporter discusses",
        }.get(role, "Team discussion")
        body = str(data.get("text") or "")
        stance = str(data.get("stance") or "")
        facts = ["AI discussion", f"model {data.get('model') or '-'}"]
        generated_label = "AI discussion"
        generated = True
        card = None
    elif kind == "thread.note":
        role = "person"
        title = "Context added"
        body = str(data.get("message") or "")
        facts = [f"by {data.get('by', 'a person')}"]
    elif kind == "note":
        raw_body = str(data.get("message") or "")
        if data.get("model"):
            role = "builder"
            title = "Proposal received"
            paths = data.get("paths") or []
            body = f"{data.get('model')} proposed a change to {len(paths)} file(s)."
            facts = [str(item) for item in paths]
        elif "v0" in raw_body and "release gate" in raw_body:
            role = "system"
            title = "Proof ready"
            body = "proof is ready; gate 2 is the next step"
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
            card = {
                "kind": "question",
                "prompt": "Release this commit?",
                "options": options,
            }
        else:
            role = "system"
            title = "Note"
            body = raw_body
    elif kind == "decision.shadow":
        role = "system"
        title = "LAIX shadow decision"
        body = f"{data.get('gate', 'gate')}: {data.get('reason_code', '')}"
        facts = [f"agree {data.get('agree', '—')}"]
    elif kind in ("wait.started", "wait.woken", "wait.expired"):
        role = "system"
        title = {
            "wait.started": "Waiting",
            "wait.woken": "Woke up",
            "wait.expired": "Wait expired",
        }[kind]
        body = str(data.get("wake_on") or data.get("on") or "")
    elif kind.startswith("memory."):
        role = "system"
        title = {
            "memory.reported": "PPMA synced",
            "memory.failed": "PPMA failed",
            "memory.recalled": "Memory recall",
            "memory.recall_failed": "Memory recall failed",
        }.get(kind, "Memory")
        body = str(data.get("error") or data.get("via") or "")
        facts = [f"{len(data.get('statements') or [])} statement(s)"]
        tone = "bad" if kind.endswith("failed") else ""
    elif kind == "state.changed":
        target = str(data.get("to") or "")
        if target not in ("blocked", "released", "reverted"):
            return None
        role = "system"
        title = f"State: {target}"
        body = str(data.get("reason") or "")
        tone = "bad" if target in ("blocked", "reverted") else "ok"
    elif kind == "preview.finished":
        role = "verifier"
        title = "Preview finished"
        body = f"Exit code {data.get('exit_code', '?')}."
        tone = "ok" if data.get("exit_code") == 0 else "bad"
    else:
        return None

    return {
        "seq": event.seq,
        "at": event.ts.isoformat(),
        "role": role,
        "type": kind,
        "title": title,
        "body": body,
        "facts": [item for item in facts if item],
        "tone": tone,
        "generated": bool(data.get("generated")) or generated,
        "generated_label": generated_label,
        "stance": stance,
        "card": card,
    }


def _thread(task: Task, events: list[Event]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event in events:
        message = _thread_message(event, task)
        if message is not None:
            messages.append(message)
    return messages


def _thread_rail(
    task: Task,
    events: list[Event],
    run: dict[str, Any] | None,
    evidence: dict[str, Any] | None,
    release: dict[str, Any],
    delivery: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
    team: dict[str, Any],
    verifier: dict[str, Any],
) -> dict[str, Any]:
    gates = [event.data for event in events if event.type == "gate.decided"]
    people = sorted({str(item.get("by") or "cli") for item in gates})
    owners = ((evidence or {}).get("risk") or {}).get("owners") or []
    challenge = (evidence or {}).get("challenge") or {}
    verdict = (evidence or {}).get("verdict") or {}
    agents = [
        {
            "role": "builder",
            "name": str((evidence or {}).get("model") or "—"),
            "detail": str((evidence or {}).get("provider") or "—"),
            "tone": "",
        },
        {
            "role": "challenger",
            "name": str(challenge.get("model") or "—"),
            "detail": "allow" if challenge.get("allow") else "block" if challenge else "not run",
            "tone": "ok" if challenge.get("allow") else "bad" if challenge else "",
        },
        {
            "role": "verifier",
            "name": str(verifier.get("name") or "local"),
            "detail": str(verifier.get("isolation") or "process"),
            "tone": "",
        },
        {
            "role": "team",
            "name": "inspector + challenger + reporter",
            "detail": str((team.get("latest") or {}).get("verdict") or "not run"),
            "tone": "ok"
            if (team.get("latest") or {}).get("verdict") == "allow"
            else "bad"
            if team.get("latest")
            else "",
        },
    ]
    deliverables = [
        {
            "label": "Proof",
            "value": str((evidence or {}).get("proof_sha256") or "—")[:12],
            "href": "",
        },
        {"label": "Commit", "value": str((run or {}).get("base_commit") or "—")[:12], "href": ""},
        {"label": "Branch", "value": str((delivery or {}).get("branch") or "—"), "href": ""},
        {
            "label": "Pull request",
            "value": str((delivery or {}).get("pr_url") or "—"),
            "href": str((delivery or {}).get("pr_url") or ""),
        },
        {
            "label": "Release",
            "value": "released" if release.get("released") else "not released",
            "href": "",
        },
        {
            "label": "Confirmation",
            "value": "pass"
            if (confirmation or {}).get("ok")
            else "fail"
            if confirmation
            else "not run",
            "href": "",
        },
    ]
    checks = [
        {
            "label": "Policy",
            "value": "pass" if ((evidence or {}).get("policy") or {}).get("ok") else "fail",
        },
        {
            "label": "Verdict",
            "value": "allow" if verdict.get("allow") else "block" if evidence else "—",
        },
        {
            "label": "Challenge",
            "value": "allow" if challenge.get("allow") else "block" if challenge else "not run",
        },
        {"label": "Team", "value": str((team.get("latest") or {}).get("verdict") or "not run")},
        {
            "label": "Confirmation",
            "value": "pass"
            if (confirmation or {}).get("ok")
            else "fail"
            if confirmation
            else "not run",
        },
    ]
    return {
        "task": {
            "id": task.id,
            "state": task.state.value,
            "product": task.product,
            "source": f"{task.source.kind.value}:{task.source.ref}",
            "title": task.source.title,
        },
        "factory": {
            "flow": task.flow,
            "run": str((run or {}).get("run_id") or "—"),
            "base_commit": str((run or {}).get("base_commit") or "—")[:12],
            "checks_sha": str((run or {}).get("checks_sha") or "—")[:12],
        },
        "people": people or ["—"],
        "owners": owners,
        "agents": agents,
        "deliverables": deliverables,
        "checks": checks,
        "cost": {
            "tokens": int((evidence or {}).get("tokens") or 0),
            "usd": float((evidence or {}).get("usd") or 0),
            "duration_ms": int((evidence or {}).get("duration_ms") or 0),
        },
    }
