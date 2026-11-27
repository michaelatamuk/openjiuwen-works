"""A local benchmark for the pipeline itself.

A dataset is a JSONL file of cases: a repository, a scenario set, a recorded harness trace and the
expected outcome. Each case runs in its own isolated home through the real supervisor; the
report says how many reached the expected state, whether the proof is bound and what it cost.

This is not a SWE-bench score. It measures the pipeline on cases you supply; a SWE-bench
adapter would have to convert its instances into this shape.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from works.adapters.harness.fake import FakeHarness
from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.supervisor import Supervisor
from works.config.paths import WorksPaths
from works.domain.enums import SourceKind
from works.domain.errors import WorksError
from works.domain.evidence import Evidence
from works.domain.task import Source


@dataclass(frozen=True)
class Case:
    id: str
    repo: Path
    scenario_set: Path
    trace: Path
    ref: str = ""
    title: str = ""
    product: str = "openjiuwen"
    flow: str = "fix-issue"
    expect_state: str = "proved"
    expect_verdict: bool | None = True


@dataclass(frozen=True)
class CaseResult:
    id: str
    ok: bool
    state: str = ""
    verdict_allow: bool | None = None
    proof_bound: bool = False
    usd: float = 0.0
    duration_ms: int = 0
    error: str = ""


@dataclass(frozen=True)
class BenchResult:
    cases: int = 0
    resolved: int = 0
    bound: int = 0
    total_usd: float = 0.0
    results: list[CaseResult] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.resolved / self.cases if self.cases else 0.0


def load_cases(path: Path) -> list[Case]:
    base = path.resolve().parent
    cases: list[Case] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            raw: object = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorksError(f"{path}: line {number} is not JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise WorksError(f"{path}: line {number} must be an object")
        missing = [key for key in ("id", "repo", "scenario_set", "trace") if not raw.get(key)]
        if missing:
            raise WorksError(f"{path}: line {number} is missing {', '.join(missing)}")
        cases.append(
            Case(
                id=str(raw["id"]),
                repo=_resolve(base, str(raw["repo"])),
                scenario_set=_resolve(base, str(raw["scenario_set"])),
                trace=_resolve(base, str(raw["trace"])),
                ref=str(raw.get("ref") or raw["id"]),
                title=str(raw.get("title") or raw["id"]),
                product=str(raw.get("product") or "openjiuwen"),
                flow=str(raw.get("flow") or "fix-issue"),
                expect_state=str(raw.get("expect_state") or "proved"),
                expect_verdict=raw.get("expect_verdict", True),
            )
        )
    return cases


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def run_bench(
    cases: list[Case],
    *,
    workdir: Path | None = None,
    keep: bool = False,
) -> BenchResult:
    root = (
        Path(tempfile.mkdtemp(prefix="works-bench-", dir=workdir))
        if workdir
        else Path(tempfile.mkdtemp(prefix="works-bench-"))
    )
    results: list[CaseResult] = []
    try:
        for case in cases:
            results.append(_run_case(case, root / case.id))
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
    return BenchResult(
        cases=len(results),
        resolved=sum(1 for item in results if item.ok),
        bound=sum(1 for item in results if item.proof_bound),
        total_usd=round(sum(item.usd for item in results), 4),
        results=results,
    )


def _run_case(case: Case, home: Path) -> CaseResult:
    if not case.repo.is_dir():
        return CaseResult(id=case.id, ok=False, error=f"repository not found: {case.repo}")
    if not case.scenario_set.is_file():
        return CaseResult(
            id=case.id, ok=False, error=f"scenario set not found: {case.scenario_set}"
        )
    if not case.trace.is_file():
        return CaseResult(id=case.id, ok=False, error=f"trace not found: {case.trace}")
    paths = WorksPaths(home).ensure()
    queue = Queue(paths)
    try:
        task, _ = queue.submit(
            source=Source(kind=SourceKind.MANUAL, ref=case.ref, title=case.title),
            flow=case.flow,
            product=case.product,
            repo=str(case.repo),
        )
        supervisor = Supervisor(
            paths=paths,
            queue=queue,
            ledger=Ledger(paths.ledger),
            harness=FakeHarness(case.trace),
            runner=SubprocessRunner(),
        )
        record = asyncio.run(
            supervisor.run(task.id, scenario_set=case.scenario_set, approve_plan=True)
        )
        evidence = Evidence.model_validate_json(
            (paths.run_dir(record.run_id) / "evidence.json").read_text(encoding="utf-8")
        )
    except (WorksError, OSError, ValueError) as exc:
        return CaseResult(id=case.id, ok=False, error=str(exc))
    allow = evidence.verdict.allow if evidence.verdict else None
    bound = bool(evidence.proof_sha256)
    ok = (
        record.state.value == case.expect_state
        and bound
        and (case.expect_verdict is None or allow == case.expect_verdict)
    )
    return CaseResult(
        id=case.id,
        ok=ok,
        state=record.state.value,
        verdict_allow=allow,
        proof_bound=bound,
        usd=record.usd,
        duration_ms=record.duration_ms,
    )
