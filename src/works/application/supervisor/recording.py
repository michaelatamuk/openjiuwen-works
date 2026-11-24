"""Writing the evidence page, run record, ledger row and memory update."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from works.adapters.git.repo import GitRepo
from works.application import run_evidence
from works.application.memory.ppma import NullMemory
from works.application.run_context import RunContext
from works.application.run_evidence import collect_diff, collect_findings
from works.config.logging import get_logger
from works.domain.evidence import write_evidence
from works.domain.records import (
    LedgerRow,
    RunRecord,
)

if TYPE_CHECKING:
    from works.application.supervisor.core import Supervisor

LOG = get_logger("supervisor")


def _finish(sup: Supervisor, ctx: RunContext, repo: GitRepo) -> RunRecord:
    finished = sup._clock()
    duration_ms = int((finished - ctx.started_at).total_seconds() * 1000)
    state = sup._current_state(ctx)
    files_changed, stats, diff = collect_diff(sup._runner, ctx.worktree)
    run_totals = run_evidence.totals(ctx)
    findings = collect_findings(sup._queue, ctx.task.id)
    verifier_name = str(getattr(sup._verifier, "name", "local"))
    verifier_isolation = str(getattr(sup._verifier, "isolation", "process"))
    draft = run_evidence.build_evidence(
        ctx,
        state=state,
        duration_ms=duration_ms,
        totals=run_totals,
        findings=findings,
        files_changed=files_changed,
        stats=stats,
        diff=diff,
        verifier_name=verifier_name,
        verifier_isolation=verifier_isolation,
    )
    from works.application.observability.features import feature_summary

    features = feature_summary(Path(ctx.task.repo), draft.model_dump(mode="json"))["features"]
    evidence = draft.model_copy(update={"features": features}).bind()
    _, md_path = write_evidence(ctx.run_dir, evidence)
    record = run_evidence.build_record(
        ctx,
        state=state,
        duration_ms=duration_ms,
        finished=finished,
        totals=run_totals,
        verifier_name=verifier_name,
        verifier_isolation=verifier_isolation,
        evidence_md=str(md_path),
        attempts=sup._queue.load(ctx.task.id).attempts,
    )
    (ctx.run_dir / "run.json").write_text(
        record.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    if ctx.commands:
        with (ctx.run_dir / "commands.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
            for command in ctx.commands:
                handle.write(command.model_dump_json() + "\n")
    verdict_label = None
    if ctx.verdict is not None:
        verdict_label = "allow" if ctx.verdict.allow else "block"
    sup._ledger.append(
        LedgerRow(
            task_id=ctx.task.id,
            run_id=ctx.run_id,
            state=state,
            verdict=verdict_label,
            tokens=run_totals.tokens,
            usd=run_totals.usd,
        )
    )
    try:
        sup._memory.record(
            task=sup._queue.load(ctx.task.id),
            record=record,
            evidence=evidence,
        )
    except Exception as exc:
        LOG.warning("memory was not updated: %s", exc, extra={"run_id": ctx.run_id})
        sup._queue.append(
            ctx.task.id,
            "memory.failed",
            {"run_id": ctx.run_id, "error": str(exc)[:500]},
        )
    else:
        if not isinstance(sup._memory, NullMemory):
            sup._queue.append(
                ctx.task.id,
                "memory.reported",
                {"run_id": ctx.run_id, "app": "ppma", "via": "run"},
            )
    LOG.info(
        "run finished",
        extra={"run_id": ctx.run_id, "task_id": ctx.task.id, "duration_ms": duration_ms},
    )
    return record
