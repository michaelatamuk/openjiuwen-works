"""Turning a finished run context into its proof, record and cost totals."""

from __future__ import annotations

import logging
import platform
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from works.adapters.git.repo import GitRepo
from works.adapters.processes.runner import CommandRunner
from works.adapters.queue.store import Queue
from works.application.proof.chain import event_root
from works.application.proof.redact import redact
from works.application.run_context import RunContext
from works.config.paths import WorksPaths
from works.domain.errors import WorksError
from works.domain.evidence import DiffStatRow, Evidence
from works.domain.evidence.models import ModelCall
from works.domain.flow import GateMode
from works.domain.records import CommandRecord, Finding, RunRecord, TaskState

LOG = logging.getLogger("works.run")


@dataclass(frozen=True)
class RunTotals:
    builder_tokens: int
    builder_usd: float
    verifier_tokens: int
    verifier_usd: float
    tokens: int
    usd: float
    verification_share: float
    provider_split: bool
    credential_split: bool


def totals(ctx: RunContext) -> RunTotals:
    proposal = ctx.proposal
    builder_tokens = proposal.tokens if proposal else 0
    builder_usd = proposal.usd if proposal else 0.0
    verifier_tokens = ctx.challenge.tokens if ctx.challenge else 0
    verifier_usd = ctx.challenge.usd if ctx.challenge else 0.0
    tokens = builder_tokens + verifier_tokens
    usd = builder_usd + verifier_usd
    return RunTotals(
        builder_tokens=builder_tokens,
        builder_usd=builder_usd,
        verifier_tokens=verifier_tokens,
        verifier_usd=verifier_usd,
        tokens=tokens,
        usd=usd,
        verification_share=round(verifier_tokens / tokens, 4) if tokens else 0.0,
        provider_split=bool(
            proposal is not None
            and ctx.challenge is not None
            and ctx.challenge.provider != proposal.provider
        ),
        credential_split=bool(ctx.challenge and ctx.challenge.credential_split),
    )


def collect_diff(
    runner: CommandRunner, worktree: Path | None
) -> tuple[list[str], list[DiffStatRow], str]:
    files_changed: list[str] = []
    stats: list[DiffStatRow] = []
    diff = ""
    if worktree is not None and worktree.exists():
        repo = GitRepo(worktree, runner)
        try:
            files_changed = repo.changed_files(worktree)
            stats = [DiffStatRow.from_stat(stat) for stat in repo.diff_stat(worktree)]
            diff = repo.diff_text(worktree)
        except WorksError as exc:
            LOG.warning("could not collect the diff: %s", exc)
    return files_changed, stats, diff


def collect_findings(queue: Queue, task_id: str) -> list[Finding]:
    findings: list[Finding] = []
    for event in queue.events(task_id):
        if event.type != "finding":
            continue
        try:
            findings.append(Finding.model_validate(event.data))
        except ValidationError as exc:
            LOG.warning("ignoring a malformed finding: %s", exc)
    return findings


def _model_calls(ctx: RunContext) -> list[ModelCall]:
    """One entry per model invocation the run actually made."""
    calls: list[ModelCall] = []
    provenance = ctx.plan.get("provenance") or {}
    if provenance.get("model"):
        calls.append(
            ModelCall(
                stage="plan",
                provider=str(provenance.get("provider") or "unknown"),
                model=str(provenance["model"]),
                version=str(provenance.get("version") or "unknown"),
                tokens=int(provenance.get("tokens") or 0),
                usd=float(provenance.get("usd") or 0.0),
            )
        )
    proposal = ctx.proposal
    if proposal is not None:
        calls.append(
            ModelCall(
                stage="build",
                provider=proposal.provider,
                model=proposal.model,
                version=proposal.version,
                tokens=proposal.tokens,
                usd=proposal.usd,
            )
        )
    challenge = ctx.challenge
    if challenge is not None:
        calls.append(
            ModelCall(
                stage="verify",
                provider=challenge.provider,
                model=challenge.model,
                version=challenge.version,
                tokens=challenge.tokens,
                usd=challenge.usd,
            )
        )
    return calls


def build_evidence(
    ctx: RunContext,
    *,
    state: TaskState,
    duration_ms: int,
    totals: RunTotals,
    findings: list[Finding],
    files_changed: list[str],
    stats: list[DiffStatRow],
    diff: str,
    verifier_name: str,
    verifier_isolation: str,
    paths: WorksPaths | None = None,
) -> Evidence:
    proposal = ctx.proposal
    provenance = ctx.plan.get("provenance") or {}
    commands: list[CommandRecord] = []
    redactions: list[str] = []
    for command in ctx.commands:
        clean_out, hits_out = redact(command.stdout_tail)
        clean_err, hits_err = redact(command.stderr_tail)
        if hits_out or hits_err:
            redactions.append(f"command:{command.step}")
        commands.append(
            command.model_copy(update={"stdout_tail": clean_out, "stderr_tail": clean_err})
        )
    root = None
    seq = None
    if paths is not None:
        events = Queue(paths).events(ctx.task.id)
        if events:
            root = event_root(events)
            seq = events[-1].seq
    return Evidence(
        run_id=ctx.run_id,
        task_id=ctx.task.id,
        flow=ctx.flow.flow,
        product=ctx.flow.product,
        source=f"{ctx.task.source.kind.value}:{ctx.task.source.ref}",
        reproduction_hint=ctx.task.source.reproduction_hint,
        reproduction_command=(
            ctx.task.reproduction_command
            or (ctx.reproduction.command if ctx.reproduction is not None else [])
        ),
        reproduction_source=(
            ctx.task.reproduction_source
            or (ctx.reproduction.source if ctx.reproduction is not None else None)
        ),
        reproduction_attempts=ctx.reproduction_attempts,
        reproduction_stable=ctx.reproduction_stable,
        reproduction_env=dict(ctx.reproduction_env),
        task_kind=ctx.task.kind.value,
        base_commit=ctx.base_commit,
        checks_sha=ctx.checks_sha,
        state=state,
        stop_reason=ctx.stop_reason,
        model=proposal.model if proposal else None,
        provider=proposal.provider if proposal else None,
        verifier=verifier_name,
        verifier_isolation=verifier_isolation,
        verifier_model=ctx.challenge.model if ctx.challenge else None,
        verifier_provider=ctx.challenge.provider if ctx.challenge else None,
        provider_split=totals.provider_split,
        credential_split=totals.credential_split,
        prompt_name=proposal.prompt_name if proposal else None,
        prompt_sha256=proposal.prompt_sha256 if proposal else None,
        harness=proposal.harness if proposal else None,
        plan_id=ctx.plan.get("plan_id"),
        plan_hash=ctx.plan.get("hash"),
        plan_summary=ctx.plan.get("summary"),
        planner_mode=provenance.get("mode"),
        planner_provider=provenance.get("provider"),
        planner_model=provenance.get("model"),
        planner_tokens=int(provenance.get("tokens") or 0),
        planner_usd=float(provenance.get("usd") or 0.0),
        plan_estimated_tokens=int(ctx.plan.get("estimated_tokens") or 0),
        plan_estimated_usd=float(ctx.plan.get("estimated_usd") or 0.0),
        plan_estimated_minutes=int(ctx.plan.get("estimated_minutes") or 0),
        plan_deviations=ctx.plan_deviations,
        tokens=totals.tokens,
        usd=totals.usd,
        builder_tokens=totals.builder_tokens,
        builder_usd=totals.builder_usd,
        verifier_tokens=totals.verifier_tokens,
        verifier_usd=totals.verifier_usd,
        model_calls=_model_calls(ctx),
        verification_share=totals.verification_share,
        duration_ms=duration_ms,
        attempts=ctx.attempt,
        baseline_exit=ctx.baseline.exit_code if ctx.baseline else None,
        baseline_output_sha256=(ctx.baseline.output_sha256 if ctx.baseline else None),
        skipped_checks=[node.id for node in ctx.flow.nodes if node.mode is GateMode.OFF],
        event_root=root,
        event_seq=seq,
        redactions=redactions,
        runtime={
            "python": " ".join(sys.version.split()[:1]),
            "platform": platform.platform(),
            "engine": proposal.version if proposal is not None else "unknown",
            "schema": "1",
        },
        files_changed=files_changed,
        diff_stat=stats,
        policy=ctx.policy,
        risk=ctx.risk,
        decision=ctx.decisions[-1] if ctx.decisions else None,
        reproduce=ctx.reproduce,
        test=ctx.test,
        preview=ctx.preview,
        artifacts=ctx.artifacts,
        memory_recall=ctx.memory_recall,
        verdict=ctx.verdict,
        challenge=ctx.challenge,
        findings=findings,
        would_block=ctx.would_block,
        diff=diff,
    )


def build_record(
    ctx: RunContext,
    *,
    state: TaskState,
    duration_ms: int,
    finished: datetime,
    totals: RunTotals,
    verifier_name: str,
    verifier_isolation: str,
    evidence_md: str,
    attempts: int,
) -> RunRecord:
    proposal = ctx.proposal
    provenance = ctx.plan.get("provenance") or {}
    last_decision = ctx.decisions[-1] if ctx.decisions else None
    return RunRecord(
        run_id=ctx.run_id,
        task_id=ctx.task.id,
        flow=ctx.flow.flow,
        state=state,
        stop_reason=ctx.stop_reason,
        base_commit=ctx.base_commit,
        checks_sha=ctx.checks_sha,
        task_kind=ctx.task.kind.value,
        risk_level=ctx.risk.level.value if ctx.risk is not None else None,
        risk_reasons=ctx.risk.reasons if ctx.risk is not None else [],
        decision_verb=last_decision.verb if last_decision is not None else None,
        decision_id=last_decision.decision_id if last_decision is not None else None,
        model=proposal.model if proposal else None,
        provider=proposal.provider if proposal else None,
        prompt_sha256=proposal.prompt_sha256 if proposal else None,
        harness=proposal.harness if proposal else None,
        plan_id=ctx.plan.get("plan_id"),
        plan_hash=ctx.plan.get("hash"),
        planner_mode=provenance.get("mode"),
        planner_provider=provenance.get("provider"),
        planner_model=provenance.get("model"),
        planner_tokens=int(provenance.get("tokens") or 0),
        planner_usd=float(provenance.get("usd") or 0.0),
        plan_estimated_tokens=int(ctx.plan.get("estimated_tokens") or 0),
        plan_estimated_usd=float(ctx.plan.get("estimated_usd") or 0.0),
        plan_estimated_minutes=int(ctx.plan.get("estimated_minutes") or 0),
        plan_deviations=ctx.plan_deviations,
        verifier=verifier_name,
        verifier_isolation=verifier_isolation,
        verifier_model=ctx.challenge.model if ctx.challenge else None,
        verifier_provider=ctx.challenge.provider if ctx.challenge else None,
        provider_split=totals.provider_split,
        credential_split=totals.credential_split,
        attempts=attempts,
        tokens=totals.tokens,
        usd=totals.usd,
        builder_tokens=totals.builder_tokens,
        builder_usd=totals.builder_usd,
        verifier_tokens=totals.verifier_tokens,
        verifier_usd=totals.verifier_usd,
        verification_share=totals.verification_share,
        started_at=ctx.started_at,
        finished_at=finished,
        duration_ms=duration_ms,
        evidence_md=evidence_md,
    )
