"""The right rail: people, agents, deliverables, checks and cost."""

from __future__ import annotations

from typing import Any

from works.domain.records import Event, Task


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
