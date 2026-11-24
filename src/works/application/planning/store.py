"""Plan hashing, construction and persistence."""

from __future__ import annotations

from pathlib import Path

from works.adapters.queue.store import atomic_write
from works.application.planning.context import PlannerContext
from works.application.planning.render import plan_brief, plan_markdown
from works.config.paths import WorksPaths
from works.domain.base import utcnow
from works.domain.errors import ConfigError, NotFoundError
from works.domain.plan import (
    PlanCritique,
    PlanMode,
    PlanProposal,
    PlanProvenance,
    PlanStatus,
    PlanValidation,
    PlanVersion,
    plan_hash,
)

__all__ = ["PlanStore", "make_plan_version", "plan_brief", "plan_markdown"]


def make_plan_version(
    context: PlannerContext,
    proposal: PlanProposal,
    *,
    version: int,
    mode: PlanMode,
    provenance: PlanProvenance,
    validation: PlanValidation,
    critique: PlanCritique | None = None,
    status: PlanStatus | None = None,
) -> PlanVersion:
    plan = PlanVersion(
        plan_id=f"p-{context.task_id}-v{version}",
        task_id=context.task_id,
        version=version,
        status=status or (PlanStatus.VALIDATED if validation.ok else PlanStatus.DRAFT),
        flow=context.flow.flow,
        product=context.product,
        base_commit=context.base_commit,
        checks_sha=context.checks_sha,
        checks_source=context.checks_source,
        scenario_set=str(context.scenario_set),
        scenario_ids=[scenario.id for scenario in context.scenarios.scenarios],
        summary=proposal.summary,
        assumptions=proposal.assumptions,
        open_questions=proposal.open_questions,
        notes=proposal.notes,
        steps=proposal.steps,
        risks=proposal.risks,
        verification=proposal.verification,
        rollback=proposal.rollback,
        estimated_tokens=proposal.estimated_tokens,
        estimated_usd=proposal.estimated_usd,
        estimated_minutes=proposal.estimated_minutes,
        requirements_md=proposal.requirements_md,
        design_md=proposal.design_md,
        tasks_md=proposal.tasks_md,
        provenance=provenance,
        validation=validation,
        critique=critique,
    )
    return plan.model_copy(update={"hash": plan_hash(plan)})


class PlanStore:
    """Immutable plan versions under the task directory."""

    def __init__(self, paths: WorksPaths) -> None:
        self._paths = paths

    def directory(self, task_id: str) -> Path:
        return self._paths.task_dir(task_id) / "plans"

    def _path(self, task_id: str, version: int) -> Path:
        return self.directory(task_id) / f"v{version}.json"

    def _shadow_path(self, task_id: str, version: int) -> Path:
        return self.directory(task_id) / f"shadow-v{version}.json"

    def versions(self, task_id: str) -> list[int]:
        directory = self.directory(task_id)
        if not directory.exists():
            return []
        versions: list[int] = []
        for path in directory.glob("v*.json"):
            try:
                versions.append(int(path.stem[1:]))
            except ValueError:
                continue
        return sorted(versions)

    def next_version(self, task_id: str) -> int:
        versions = self.versions(task_id)
        return (versions[-1] + 1) if versions else 1

    def save(self, plan: PlanVersion) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._path(plan.task_id, plan.version)
        if path.exists():
            raise ConfigError(f"plan version {plan.version} already exists for {plan.task_id}")
        atomic_write(path, plan.model_dump_json(indent=2) + "\n")
        atomic_write(
            path.with_suffix(".md"),
            plan_markdown(plan) + "\n",
        )
        for suffix, text in (
            ("requirements.md", plan.requirements_md),
            ("design.md", plan.design_md),
            ("tasks.md", plan.tasks_md),
        ):
            if text.strip():
                atomic_write(path.with_name(f"{path.stem}.{suffix}"), text + "\n")
        return plan

    def save_alternative(self, plan: PlanVersion, label: str) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        version = len(list(directory.glob(f"alt-{label}-v*.json"))) + 1
        alternative = plan.model_copy(
            update={
                "plan_id": f"alt-{label}-{plan.task_id}-v{version}",
                "version": version,
                "status": PlanStatus.ALTERNATIVE,
            }
        )
        path = directory / f"alt-{label}-v{version}.json"
        atomic_write(path, alternative.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(alternative) + "\n")
        return alternative

    def alternatives(self, task_id: str) -> dict[str, PlanVersion]:
        directory = self.directory(task_id)
        found: dict[str, PlanVersion] = {}
        if not directory.exists():
            return found
        for path in sorted(directory.glob("alt-*-v*.json")):
            plan = PlanVersion.model_validate_json(path.read_text(encoding="utf-8"))
            found[plan.plan_id] = plan
        return found

    def save_shadow(self, plan: PlanVersion) -> PlanVersion:
        directory = self.directory(plan.task_id)
        directory.mkdir(parents=True, exist_ok=True)
        version = len(list(directory.glob("shadow-v*.json"))) + 1
        shadow = plan.model_copy(
            update={"plan_id": f"shadow-{plan.task_id}-v{version}", "version": version}
        )
        path = self._shadow_path(plan.task_id, version)
        atomic_write(path, shadow.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(shadow) + "\n")
        return shadow

    def approve(self, task_id: str, *, plan_id: str, plan_hash: str, by: str) -> PlanVersion:
        plan = self.load(task_id)
        if plan.plan_id != plan_id or plan.hash != plan_hash:
            raise ConfigError("the plan changed before it was approved; re-plan first")
        updated = plan.model_copy(
            update={
                "status": PlanStatus.APPROVED,
                "approved_by": by,
                "approved_at": utcnow(),
            }
        )
        path = self._path(task_id, plan.version)
        atomic_write(path, updated.model_dump_json(indent=2) + "\n")
        atomic_write(path.with_suffix(".md"), plan_markdown(updated) + "\n")
        return updated

    def mark_superseded(self, task_id: str, plan_id: str) -> None:
        for version in self.versions(task_id):
            plan = self.load(task_id, version)
            if plan.plan_id != plan_id:
                continue
            updated = plan.model_copy(update={"status": PlanStatus.SUPERSEDED})
            path = self._path(task_id, plan.version)
            atomic_write(path, updated.model_dump_json(indent=2) + "\n")
            atomic_write(path.with_suffix(".md"), plan_markdown(updated) + "\n")
            return

    def load(self, task_id: str, version: int | None = None) -> PlanVersion:
        selected = version or (self.versions(task_id)[-1] if self.versions(task_id) else None)
        if selected is None:
            raise NotFoundError(f"task {task_id} has no plan")
        path = self._path(task_id, selected)
        if not path.exists():
            raise NotFoundError(f"task {task_id} has no plan version {selected}")
        try:
            return PlanVersion.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ConfigError(f"{path} is not a valid plan: {exc}") from exc

    def shadow(self, task_id: str) -> PlanVersion | None:
        paths = sorted(self.directory(task_id).glob("shadow-v*.json"))
        if not paths:
            return None
        return PlanVersion.model_validate_json(paths[-1].read_text(encoding="utf-8"))

    def all(self, task_id: str) -> list[PlanVersion]:
        return [self.load(task_id, version) for version in self.versions(task_id)]
