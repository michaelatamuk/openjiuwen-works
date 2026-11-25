from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from works.application.run_evidence import RunTotals, build_record
from works.domain.records import StopReason, TaskState


def test_the_run_record_keeps_the_prompt_hash() -> None:
    proposal = SimpleNamespace(
        model="deepseek-chat", provider="deepseek", prompt_sha256="a" * 64, harness="native"
    )
    ctx = SimpleNamespace(
        run_id="r-20260101T000000-abcdef",
        task=SimpleNamespace(id="t-1", kind=SimpleNamespace(value="fix")),
        flow=SimpleNamespace(flow="fix-issue"),
        stop_reason=StopReason.COMPLETED,
        base_commit=None,
        checks_sha=None,
        risk=None,
        decisions=[],
        plan={},
        plan_deviations=[],
        proposal=proposal,
        challenge=None,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    totals = RunTotals(
        builder_tokens=10,
        builder_usd=0.001,
        verifier_tokens=0,
        verifier_usd=0.0,
        tokens=10,
        usd=0.001,
        verification_share=0.0,
        provider_split=False,
        credential_split=False,
    )

    record = build_record(
        ctx,  # type: ignore[arg-type]
        state=TaskState.PROVED,
        duration_ms=1,
        finished=datetime(2026, 1, 1, tzinfo=UTC),
        totals=totals,
        verifier_name="local",
        verifier_isolation="process",
        evidence_md="# evidence",
        attempts=1,
    )

    assert record.prompt_sha256 == "a" * 64
    assert record.harness == "native"
    assert record.model == "deepseek-chat"
