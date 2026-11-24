from __future__ import annotations

from pathlib import Path

from tests.contract.canonicalize import canonicalize


def test_masks_ids_timestamps_hashes_and_commits() -> None:
    payload = {
        "task": {
            "id": "t-0123456789ab",
            "created_at": "2026-11-21T09:00:00+00:00",
            "updated_at": "2026-11-21T09:05:00.123456+00:00",
        },
        "run": {
            "run_id": "r-20261121T090000-abcdef",
            "base_commit": "abcdef1234567890",
            "checks_sha": "a" * 64,
            "finished_at": "2026-11-21T09:10:00Z",
        },
    }

    assert canonicalize(payload) == {
        "task": {"id": "<task-id>", "created_at": "<timestamp>", "updated_at": "<timestamp>"},
        "run": {
            "run_id": "<run-id>",
            "base_commit": "<commit>",
            "checks_sha": "<sha256>",
            "finished_at": "<timestamp>",
        },
    }


def test_task_id_in_a_string_and_plan_id_are_masked() -> None:
    payload = {
        "plan_id": "p-t-0123456789ab-v2",
        "source": "manual:GH-42",
        "previous_task_id": "t-0123456789ab",
    }

    assert canonicalize(payload) == {
        "plan_id": "p-<task-id>-v2",
        "source": "manual:GH-42",
        "previous_task_id": "<task-id>",
    }


def test_artifact_urls_and_proof_strings_are_masked() -> None:
    payload = {
        "url": "/api/v1/tasks/t-0123456789ab/artifacts/shot.png",
        "artifact": "commit abc1234567",
        "proof": "proof deadbeef12",
        "sha": "b" * 64,
    }

    canonical = canonicalize(payload)

    assert canonical["url"] == "/api/tasks/<task-id>/artifacts/shot.png"
    assert canonical["artifact"] == "commit <commit>"
    assert canonical["proof"] == "proof <sha256>"
    assert canonical["sha"] == "<sha256>"


def test_home_and_repo_paths_are_masked_in_both_separators() -> None:
    home = Path(r"C:\Work\demo")
    repo = Path(r"C:\Work\demo\repo")
    payload = {
        "root": str(home),
        "repo": str(repo),
        "mixed": str(repo).replace("\\", "/") + "/calc/core.py",
    }

    canonical = canonicalize(payload, home=home, repo=repo)

    assert canonical["root"] == "<home>"
    assert canonical["repo"] == "<repo>"
    assert canonical["mixed"] == "<repo>/calc/core.py"


def test_nested_lists_and_unknown_strings_are_recursed_but_kept() -> None:
    payload = {
        "timeline": [
            {"ts": "2026-11-21T09:00:00+00:00", "type": "state.changed"},
            {"ts": "not-a-timestamp", "type": "note"},
        ],
        "labels": ["Reported", "Fixed"],
    }

    assert canonicalize(payload) == {
        "timeline": [
            {"ts": "<timestamp>", "type": "state.changed"},
            {"ts": "not-a-timestamp", "type": "note"},
        ],
        "labels": ["Reported", "Fixed"],
    }


def test_empty_commit_and_null_values_are_preserved() -> None:
    payload = {"commit": "", "sha256": "", "run": None}

    assert canonicalize(payload) == {"commit": "", "sha256": "", "run": None}
