"""Render a versioned plan as a model brief or a markdown page."""

from __future__ import annotations

from works.domain.plan import PlanVersion


def plan_brief(plan: PlanVersion) -> str:
    """A compact, model-readable brief of the approved plan."""
    lines = [f"Summary: {plan.summary}"]
    for step in plan.steps:
        details = [f"node={step.node}", f"done_when={step.done_when or 'not stated'}"]
        if step.files:
            details.append(f"files={', '.join(step.files)}")
        if step.reads:
            details.append(f"reads={', '.join(step.reads)}")
        if step.commands:
            details.append(f"commands={', '.join(step.commands)}")
        lines.append(f"- {step.title} ({'; '.join(details)})")
    if plan.verification:
        lines.append("Verification: " + "; ".join(plan.verification))
    if plan.assumptions:
        lines.append("Assumptions: " + "; ".join(plan.assumptions))
    if plan.open_questions:
        lines.append("Open questions: " + "; ".join(plan.open_questions))
    if plan.risks:
        lines.append("Risks: " + "; ".join(plan.risks))
    if plan.rollback:
        lines.append(f"Rollback: {plan.rollback}")
    return "\n".join(lines)


def plan_markdown(plan: PlanVersion) -> str:
    lines = [
        f"# Plan {plan.plan_id}",
        "",
        f"- Task: `{plan.task_id}`",
        f"- Flow: `{plan.flow}` / {plan.product}",
        f"- Status: `{plan.status.value}`",
        f"- Base commit: `{plan.base_commit}`",
        f"- Checks: `{plan.checks_sha}` ({plan.checks_source})",
        f"- Scenarios: {', '.join(plan.scenario_ids) or 'none'}",
        f"- Planner: `{plan.provenance.planner}`",
        f"- Provider/model: `{plan.provenance.provider or '-'}` / `{plan.provenance.model or '-'}`",
        f"- Cost: {plan.provenance.tokens} tokens / ${plan.provenance.usd:.4f}",
        f"- Hash: `{plan.hash}`",
        "",
        "## Summary",
        "",
        plan.summary,
        "",
    ]
    if plan.assumptions:
        lines += ["## Assumptions", "", *[f"- {item}" for item in plan.assumptions], ""]
    if plan.open_questions:
        lines += ["## Open questions", "", *[f"- {item}" for item in plan.open_questions], ""]
    if plan.notes:
        lines += ["## Notes", "", *[f"- {item}" for item in plan.notes], ""]
    if plan.requirements_md:
        lines += ["## Requirements", "", plan.requirements_md, ""]
    if plan.design_md:
        lines += ["## Design", "", plan.design_md, ""]
    if plan.tasks_md:
        lines += ["## Tasks", "", plan.tasks_md, ""]
    lines += ["## Steps", ""]
    for step in plan.steps:
        lines += [
            f"### {step.id} · {step.node} · {step.title}",
            "",
            step.intent,
            "",
            f"- Done when: {step.done_when or 'not stated'}",
            f"- Files: {', '.join(step.files) or 'none named'}",
            f"- Reads: {', '.join(step.reads) or 'none named'}",
            f"- Commands: {', '.join(step.commands) or 'none'}",
            f"- Risk: {step.risk}",
            "",
        ]
    if plan.risks:
        lines += ["## Risks", "", *[f"- {item}" for item in plan.risks], ""]
    if plan.verification:
        lines += ["## Verification", "", *[f"- {item}" for item in plan.verification], ""]
    lines += ["## Rollback", "", plan.rollback, ""]
    if plan.validation is not None:
        lines += [
            "## Lint",
            "",
            f"- OK: `{plan.validation.ok}`",
            *[f"- Error: {item}" for item in plan.validation.errors],
            *[f"- Warning: {item}" for item in plan.validation.warnings],
            "",
        ]
    if plan.critique is not None:
        lines += [
            "## Critique",
            "",
            f"- Allow: `{plan.critique.allow}`",
            f"- Score: {plan.critique.score:.2f}",
            *[f"- Finding: {item}" for item in plan.critique.findings],
            *[f"- Concern: {item}" for item in plan.critique.concerns],
            "",
        ]
    lines += ["## Provenance", "", "```json", plan.provenance.model_dump_json(indent=2), "```", ""]
    return "\n".join(lines)
