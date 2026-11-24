"""Thread message handlers: planning and the plan gate."""

from __future__ import annotations

from works.domain.records import Event, Task
from works.interfaces.api.presenters.thread.messages.types import Fields


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
