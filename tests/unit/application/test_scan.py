from __future__ import annotations

import sys
from pathlib import Path

from works.adapters.processes.runner import CommandResult
from works.adapters.queue.store import Queue
from works.application.scan import baseline_path, parse_failures, scan_repository
from works.domain.enums import SourceKind


class FakeRunner:
    def __init__(self, *results: CommandResult) -> None:
        self._results = list(results)
        self.calls: list[tuple[list[str], Path]] = []

    def run(self, argv, cwd, *, env=None, timeout_s=600):  # type: ignore[no-untyped-def]
        self.calls.append((list(argv), cwd))
        return self._results.pop(0)


def result(exit_code: int, stdout: str = "", stderr: str = "") -> CommandResult:
    return CommandResult(
        argv=("check",),
        cwd=".",
        exit_code=exit_code,
        duration_ms=1,
        stdout=stdout,
        stderr=stderr,
    )


def test_failures_are_parsed_and_deduplicated() -> None:
    output = (
        "FAILED tests/test_a.py::test_one - AssertionError\n"
        "FAILED tests/test_a.py::test_one - AssertionError\n"
        "ERROR tests/test_b.py::test_two - setup\n"
        "1 failed, 1 error\n"
    )

    assert parse_failures(output) == [
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_two",
    ]


def test_a_new_failure_becomes_one_task(paths, repo, tmp_path: Path) -> None:
    scanner = FakeRunner(result(1, "FAILED tests/test_core.py::test_add\n"))

    first = scan_repository(paths, repo.path, "pytest -q", runner=scanner)

    assert first.new == ["tests/test_core.py::test_add"]
    assert len(first.created) == 1
    task = Queue(paths).load(first.created[0])
    assert task.source.kind is SourceKind.DETECTOR
    assert task.source.channel == "scan"
    assert task.source.ref == "scan:tests/test_core.py::test_add"


def test_the_same_failure_is_not_filed_twice(paths, repo) -> None:
    scanner = FakeRunner(
        result(1, "FAILED tests/test_core.py::test_add\n"),
        result(1, "FAILED tests/test_core.py::test_add\n"),
    )

    first = scan_repository(paths, repo.path, "pytest -q", runner=scanner)
    second = scan_repository(paths, repo.path, "pytest -q", runner=scanner)

    assert first.created
    assert second.new == []
    assert second.created == []
    assert len(Queue(paths).list_tasks()) == 1


def test_a_fixed_failure_is_removed_from_the_baseline(paths, repo) -> None:
    scanner = FakeRunner(
        result(1, "FAILED a::one\nFAILED a::two\n"),
        result(1, "FAILED a::two\n"),
    )

    scan_repository(paths, repo.path, "pytest -q", runner=scanner)
    second = scan_repository(paths, repo.path, "pytest -q", runner=scanner)

    assert second.fixed == ["a::one"]
    assert second.new == []
    assert second.failures == ["a::two"]


def test_a_green_scan_clears_everything(paths, repo) -> None:
    scanner = FakeRunner(result(1, "FAILED a::one\n"), result(0))

    scan_repository(paths, repo.path, "pytest -q", runner=scanner)
    second = scan_repository(paths, repo.path, "pytest -q", runner=scanner)

    assert second.failures == []
    assert second.fixed == ["a::one"]
    assert second.exit_code == 0


def test_a_command_failure_without_test_ids_is_one_stable_task(paths, repo) -> None:
    scanner = FakeRunner(
        result(2, "boom: cannot import calc\n"), result(2, "boom: cannot import calc\n")
    )

    first = scan_repository(paths, repo.path, "check", runner=scanner)
    second = scan_repository(paths, repo.path, "check", runner=scanner)

    assert len(first.new) == 1
    assert first.new[0].startswith("command-")
    assert second.new == []
    assert len(Queue(paths).list_tasks()) == 1


def test_a_dry_run_writes_nothing(paths, repo) -> None:
    scanner = FakeRunner(result(1, "FAILED a::one\n"))

    result_ = scan_repository(paths, repo.path, "pytest -q", runner=scanner, dry_run=True)

    assert result_.new == ["a::one"]
    assert result_.created == []
    assert not baseline_path(paths, repo.path, "pytest -q").exists()
    assert Queue(paths).list_tasks() == []


def test_the_baseline_is_keyed_by_repo_and_command(paths, repo) -> None:
    scanner = FakeRunner(result(1, "FAILED a::one\n"))

    scan_repository(paths, repo.path, "pytest -q", runner=scanner)

    assert baseline_path(paths, repo.path, "pytest -q").exists()
    assert not baseline_path(paths, repo.path, "pytest -x").exists()


def test_the_cli_scans_and_reports_json(paths, tmp_path: Path) -> None:
    from tests.unit.interfaces.cli.test_cli import invoke, payload

    repo = tmp_path / "scan-repo"
    repo.mkdir()
    (repo / "check.py").write_text(
        'print("FAILED tests/test_scan.py::test_it")\nraise SystemExit(1)\n',
        encoding="utf-8",
    )
    command = f"{sys.executable} check.py"

    first = invoke(paths, "scan", "--repo", str(repo), "--command", command, "--json")

    assert first.exit_code == 0, first.stderr
    body = payload(first)
    assert body["new"] == ["tests/test_scan.py::test_it"]
    assert len(body["created"]) == 1

    second = invoke(paths, "scan", "--repo", str(repo), "--command", command, "--json")
    assert payload(second)["new"] == []
