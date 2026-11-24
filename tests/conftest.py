from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from works.adapters.git.repo import GitRepo, init_repo
from works.adapters.harness.base import Harness
from works.adapters.harness.fake import FakeHarness
from works.adapters.processes.runner import SubprocessRunner
from works.adapters.queue.ledger import Ledger
from works.adapters.queue.store import Queue
from works.application.supervisor import Supervisor
from works.config import WorksPaths
from works.domain.records import Budget, Source, SourceKind, Task, TaskKind

FACTORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def factory_root() -> Path:
    return FACTORY_ROOT


@pytest.fixture
def paths(tmp_path: Path) -> WorksPaths:
    root = tmp_path / "works"
    workspace = WorksPaths(root).ensure()
    if not workspace.flows.exists():
        shutil.copytree(FACTORY_ROOT / "flows", workspace.flows)
    return workspace


@pytest.fixture
def make_repo(tmp_path: Path) -> Callable[..., GitRepo]:
    def build(*, fixed: bool = False, name: str = "repo") -> GitRepo:
        destination = tmp_path / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(FACTORY_ROOT / "fixtures" / "fixture-repo", destination)
        if fixed:
            core = destination / "calc" / "core.py"
            core.write_text(
                core.read_text(encoding="utf-8").replace("return a - b", "return a + b"),
                encoding="utf-8",
                newline="\n",
            )
        return init_repo(destination)

    return build


@pytest.fixture
def repo(make_repo: Callable[..., GitRepo]) -> GitRepo:
    return make_repo()


@pytest.fixture
def scenario_set(factory_root: Path) -> Path:
    return factory_root / "fixtures" / "scenarios" / "fix-add.yaml"


@pytest.fixture
def trace(factory_root: Path) -> Callable[[str], Path]:
    return lambda name: factory_root / "fixtures" / "traces" / f"{name}.json"


@pytest.fixture
def submit(paths: WorksPaths, repo: GitRepo) -> Callable[..., Task]:
    def create(
        *,
        ref: str = "GH-1",
        budget: Budget | None = None,
        repo_path: Path | None = None,
        task_kind: TaskKind = TaskKind.FIX,
    ) -> Task:
        queue = Queue(paths)
        task, _ = queue.submit(
            source=Source(kind=SourceKind.MANUAL, ref=ref, title="add subtracts"),
            flow="fix-issue",
            product="openjiuwen",
            repo=str(repo_path or repo.path),
            budget=budget,
            task_kind=task_kind,
        )
        return task

    return create


@pytest.fixture
def make_supervisor(paths: WorksPaths, trace: Callable[[str], Path]) -> Callable[..., Supervisor]:
    def build(trace_name: str = "fix-add", *, harness: Harness | None = None) -> Supervisor:
        return Supervisor(
            paths=paths,
            queue=Queue(paths),
            ledger=Ledger(paths.ledger),
            harness=harness if harness is not None else FakeHarness(trace(trace_name)),
            runner=SubprocessRunner(),
        )

    return build
