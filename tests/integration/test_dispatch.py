from __future__ import annotations

from tests.unit.interfaces.cli.test_cli import invoke, payload
from works.adapters.queue.store import Queue
from works.domain.records import Source, SourceKind, TaskState


def submit(paths, repo, ref: str) -> str:
    task, _ = Queue(paths).submit(
        source=Source(kind=SourceKind.MANUAL, ref=ref, title="add subtracts"),
        flow="fix-issue",
        product="openjiuwen",
        repo=str(repo.path),
    )
    return task.id


def dispatch(paths, scenario_set, trace):
    return invoke(
        paths,
        "dispatch",
        "--approve-plan",
        "--scenarios",
        str(scenario_set),
        "--trace",
        str(trace),
        "--json",
    )


def test_dispatch_runs_ready_tasks_once(paths, repo, scenario_set, trace) -> None:
    first = submit(paths, repo, "D-1")
    second = submit(paths, repo, "D-2")
    result = dispatch(paths, scenario_set, trace("fix-add"))
    assert result.exit_code == 0, result.stdout + result.stderr
    body = payload(result)
    assert body["selected"] == 2
    assert {item["task_id"] for item in body["runs"]} == {first, second}
    assert Queue(paths).load(first).state is TaskState.PROVED
    assert Queue(paths).load(second).state is TaskState.PROVED

    again = dispatch(paths, scenario_set, trace("fix-add"))
    assert again.exit_code == 0
    assert payload(again)["selected"] == 0
