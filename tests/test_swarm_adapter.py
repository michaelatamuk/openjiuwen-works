from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from works.adapters.git.repo import init_repo
from works.adapters.harness.base import ProposalRequest
from works.adapters.harness.swarm.harness import SwarmHarness, default_entrypoint, preflight

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "swarm_adapter.py"

FAKE = """\
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

argv = sys.argv[1:]
if "--help" in argv:
    print("fake jiuwenswarm")
    raise SystemExit(0)
cwd = Path(argv[argv.index("--cwd") + 1])
prompt = argv[argv.index("chat") + 1] if "chat" in argv else ""
if "independent reviewer" in prompt:
    if os.environ.get("FAKE_REVIEW_MUTATES"):
        (cwd / "review.txt").write_text("changed", encoding="utf-8")
    if os.environ.get("FAKE_REVIEW_BAD"):
        content = "I cannot answer with a verdict"
    else:
        content = json.dumps({"allow": True, "reason": "looks good", "concerns": []})
    print(json.dumps({"ok": True, "content": content}))
elif os.environ.get("FAKE_NO_CHANGE"):
    print(json.dumps({"ok": True, "content": "nothing to do"}))
else:
    calc = cwd / "calc.py"
    text = calc.read_text(encoding="utf-8").replace("return a - b", "return a + b")
    calc.write_text(text, encoding="utf-8")
    if os.environ.get("FAKE_USAGE"):
        usage = {
            "type": "event",
            "event": "chat.usage_metadata",
            "payload": {
                "execution_id": "exec-1",
                "metadata": {
                    "usage_metadata": {
                        "model_name": "fake-model",
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "total_tokens": 15,
                        "total_cost": 0.01,
                    }
                },
            },
        }
        print(json.dumps(usage))
        final = {
            "type": "event",
            "event": "chat.final",
            "payload": {"event_type": "chat.final", "content": "fixed"},
        }
        print(json.dumps(final))
    else:
        print(json.dumps({"ok": True, "content": "fixed"}))
"""


def _repo(tmp_path: Path) -> Path:
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    init_repo(worktree)
    return worktree


def _harness(tmp_path: Path, fake: Path, extra_env: dict[str, str] | None = None) -> SwarmHarness:
    home = tmp_path / "jiuwenswarm"
    home.mkdir(exist_ok=True)
    env = {"WORKS_SWARM_CLI": json.dumps([sys.executable, str(fake)])}
    env.update(extra_env or {})
    return SwarmHarness(
        python=Path(sys.executable),
        home=home,
        entrypoint=[str(ADAPTER)],
        env=env,
        timeout_s=30,
    )


def _request(worktree: Path) -> ProposalRequest:
    return ProposalRequest(
        task_id="t-adapter",
        source_ref="FIX-1",
        title="add subtracts",
        worktree=worktree,
        base_commit="HEAD",
    )


def _fake(tmp_path: Path) -> Path:
    path = tmp_path / "fake_swarm.py"
    path.write_text(FAKE, encoding="utf-8")
    return path


def test_the_default_entrypoint_is_the_repo_adapter(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("WORKS_SWARM_ENTRYPOINT", raising=False)

    entrypoint = default_entrypoint()

    assert Path(entrypoint[0]).name == "swarm_adapter.py"
    home = tmp_path / "home"
    home.mkdir()
    diagnostic = preflight(Path(sys.executable), home=home, entrypoint=entrypoint)
    assert diagnostic.ok is True
    assert "entrypoint started" in diagnostic.detail


def test_the_adapter_proposes_a_real_diff_end_to_end(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path))

    proposal = asyncio.run(harness.propose(_request(worktree)))

    assert proposal.applied is True
    assert proposal.touched_paths == ["calc.py"]
    assert "return a + b" in proposal.patch
    assert proposal.model == "jiuwenswarm"


def test_the_adapter_reads_usage_metadata(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path), {"FAKE_USAGE": "1"})

    proposal = asyncio.run(harness.propose(_request(worktree)))

    assert proposal.tokens == 15
    assert proposal.usd == 0.01
    assert proposal.model == "fake-model"


def test_the_adapter_challenges_the_same_worktree(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path))
    proposal = asyncio.run(harness.propose(_request(worktree)))

    challenge = asyncio.run(harness.challenge(_request(worktree), proposal))

    assert challenge.allow is True
    assert challenge.reason == "looks good"


def test_a_no_change_build_stops_instead_of_pretending(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path), {"FAKE_NO_CHANGE": "1"})

    proposal = asyncio.run(harness.propose(_request(worktree)))

    assert proposal.applied is False
    assert proposal.stop is not None
    assert "no change" in proposal.stop


def test_a_review_that_edits_the_worktree_is_refused(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path), {"FAKE_REVIEW_MUTATES": "1"})
    proposal = asyncio.run(harness.propose(_request(worktree)))

    challenge = asyncio.run(harness.challenge(_request(worktree), proposal))

    assert challenge.allow is False
    assert "review-mutated-worktree" in challenge.concerns


def test_a_non_json_verdict_is_fail_closed(tmp_path) -> None:
    worktree = _repo(tmp_path)
    harness = _harness(tmp_path, _fake(tmp_path), {"FAKE_REVIEW_BAD": "1"})
    proposal = asyncio.run(harness.propose(_request(worktree)))

    challenge = asyncio.run(harness.challenge(_request(worktree), proposal))

    assert challenge.allow is False
    assert "format" in challenge.concerns
