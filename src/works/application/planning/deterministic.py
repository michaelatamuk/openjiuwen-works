"""Deterministic plan skeleton and proposal merging."""

from __future__ import annotations

from works.application.planning.context import PlannerContext, PlannerOutput
from works.domain.flow import Node, NodeKind
from works.domain.plan import PlanMode, PlanProposal, PlanProvenance, PlanStep


def _node_step(node: Node, order: int, previous: str | None) -> PlanStep:
    kind = "deterministic command" if node.kind is NodeKind.DETERMINISTIC else "agent turn"
    intents = {
        "reproduce": "Reproduce the reported behaviour and capture the failing check.",
        "build": "Edit the minimum production code needed to make the reproduction pass.",
        "test": "Run the repository tests and the declared scenarios.",
        "challenge": "Review the diff independently and return a verdict.",
        "preview": "Run the preview and attach its artifacts.",
    }
    done = {
        "reproduce": "the reproduction fails on the base commit",
        "build": "the reproduction and tests pass",
        "test": "the tests and scenarios pass",
        "challenge": "the challenger returns allow",
        "preview": "the preview exits successfully",
    }
    commands = [node.cmd] if node.cmd else []
    return PlanStep(
        id=f"det-{order}-{node.id}",
        node=node.id,
        title=f"{node.id}: {kind}",
        intent=intents.get(node.id, f"Run the flow node {node.id!r} as declared."),
        commands=commands,
        done_when=done.get(node.id, "the node records a terminal result"),
        risk="low",
        depends_on=[previous] if previous else [],
    )


def deterministic_proposal(context: PlannerContext) -> PlanProposal:
    """The contract skeleton: one step per flow node, scenario coverage, safe defaults."""
    steps: list[PlanStep] = []
    previous: str | None = None
    for order, node in enumerate(context.flow.nodes, start=1):
        step = _node_step(node, order, previous)
        steps.append(step)
        previous = step.id
    p0 = ", ".join(context.p0_ids) or "none declared"
    p1 = ", ".join(context.p1_ids) or "none declared"
    verification = [
        "Run the flow test node.",
        f"P0 scenarios: {p0}.",
        f"P1 scenarios: {p1}.",
    ]
    if any(node.id == "challenge" for node in context.flow.nodes):
        verification.append("Run the independent challenge node.")
    return PlanProposal(
        summary=(
            f"Deterministic plan for {context.flow.flow} on {context.product}: "
            f"{len(context.flow.nodes)} flow nodes and "
            f"{len(context.scenarios.scenarios)} scenarios."
        ),
        assumptions=[
            "The flow nodes and the scenario set are the source of truth.",
            "The builder works in an isolated worktree and does not commit.",
        ],
        steps=steps,
        risks=[
            "This plan is a contract skeleton; file-level detail is chosen during the build turn."
        ],
        verification=verification,
        rollback="Discard the worktree; the builder does not commit.",
        notes=["Deterministic mode: no model planned this version."],
    )


def _normalise_steps(steps: list[PlanStep]) -> list[PlanStep]:
    seen: set[str] = set()
    normalised: list[PlanStep] = []
    for index, step in enumerate(steps, start=1):
        identifier = step.id.strip() or f"s{index}"
        candidate = identifier
        suffix = 2
        while candidate in seen:
            candidate = f"{identifier}-{suffix}"
            suffix += 1
        seen.add(candidate)
        normalised.append(step.model_copy(update={"id": candidate}))
    return normalised


def merge_proposal(
    base: PlanProposal, proposal: PlanProposal, context: PlannerContext
) -> PlanProposal:
    """Keep the deterministic contract and let a model add detail inside its nodes.

    Missing required nodes get their deterministic step back. Unknown node names are kept so the
    linter can reject them instead of silently dropping a model mistake.
    """
    by_node: dict[str, list[PlanStep]] = {}
    for step in _normalise_steps(proposal.steps):
        by_node.setdefault(step.node, []).append(step)

    base_by_node: dict[str, PlanStep] = {step.node: step for step in base.steps}
    merged: list[PlanStep] = []
    for node in context.flow.nodes:
        model_steps = by_node.get(node.id, [])
        if model_steps:
            merged.extend(model_steps)
        elif node.id in base_by_node:
            merged.append(base_by_node[node.id])
    # Unknown nodes are intentionally kept for the linter.
    for node_id, steps in by_node.items():
        if node_id not in {node.id for node in context.flow.nodes}:
            merged.extend(steps)

    def node_order(step: PlanStep) -> tuple[int, int]:
        ids = [node.id for node in context.flow.nodes]
        try:
            return (ids.index(step.node), 0)
        except ValueError:
            return (len(ids), 0)

    merged.sort(key=node_order)
    return PlanProposal(
        summary=proposal.summary.strip() or base.summary,
        assumptions=_unique([*base.assumptions, *proposal.assumptions]),
        open_questions=_unique(proposal.open_questions),
        steps=_normalise_steps(merged),
        risks=_unique(proposal.risks) or base.risks,
        verification=_unique(proposal.verification) or base.verification,
        rollback=proposal.rollback.strip() or base.rollback,
        estimated_tokens=proposal.estimated_tokens,
        estimated_usd=proposal.estimated_usd,
        estimated_minutes=proposal.estimated_minutes,
        notes=_unique(proposal.notes) or base.notes,
        requirements_md=proposal.requirements_md.strip(),
        design_md=proposal.design_md.strip(),
        tasks_md=proposal.tasks_md.strip(),
    )


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


class DeterministicPlanner:
    name = "deterministic"

    async def draft(self, context: PlannerContext) -> PlannerOutput:
        return PlannerOutput(
            proposal=deterministic_proposal(context),
            provenance=PlanProvenance(mode=PlanMode.DETERMINISTIC.value),
        )
